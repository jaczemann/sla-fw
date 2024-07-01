# This file is part of the SLA firmware
# Copyright (C) 2021-2024 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import time
from abc import abstractmethod
from asyncio import gather
from pathlib import Path
from shutil import rmtree, copyfile

from gi.repository import GLib

import pydbus
import paho.mqtt.publish as mqtt

from slafw import defines, test_runtime
from slafw.configs.unit import Nm
from slafw.errors.errors import (
    MissingUVPWM,
    MissingWizardData,
    MissingCalibrationData,
    MissingUVCalibrationData,
    ErrorSendingDataToMQTT,
    MissingExamples,
)
from slafw.errors.warnings import FactoryResetCheckFailure
from slafw.functions.files import ch_mode_owner, get_all_supported_files
from slafw.functions.system import FactoryMountedRW, reset_hostname, compute_uvpwm, set_update_channel
from slafw.wizard.actions import UserActionBroker
from slafw.wizard.checks.base import Check, WizardCheckType, SyncCheck, DangerousCheck
from slafw.wizard.setup import Configuration, Resource
from slafw.wizard.data_package import WizardDataPackage
from slafw.wizard.wizards.self_test import SelfTestWizard
from slafw.wizard.wizards.uv_calibration import UVCalibrationWizard


class ResetCheck(SyncCheck):
    def __init__(self, *args, hard_errors: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.hard_errors = hard_errors

    def task_run(self, actions: UserActionBroker):
        try:
            self.reset_task_run(actions)
            # Subtle non-asyncio delay to slow down reset check processing while providing nicer user feedback.
        except Exception as exception:
            self._logger.exception("Failed to run factory reset check: %s", type(self).__name__)
            if self.hard_errors:
                raise
            self.add_warning(FactoryResetCheckFailure(f"Failed to run factory reset check: {exception}"))

    @abstractmethod
    def reset_task_run(self, actions: UserActionBroker):
        ...


class EraseProjects(ResetCheck):
    def __init__(self, *args, **kwargs):
        super().__init__(WizardCheckType.ERASE_PROJECTS, *args, **kwargs)

    def reset_task_run(self, actions: UserActionBroker):
        rmtree(defines.internalProjectPath)
        if not Path(defines.internalProjectPath).exists():
            Path(defines.internalProjectPath).mkdir(parents=True)
            ch_mode_owner(defines.internalProjectPath)


class ResetHostname(ResetCheck):
    def __init__(self, *args, **kwargs):
        super().__init__(WizardCheckType.RESET_HOSTNAME, *args, **kwargs)

    def reset_task_run(self, actions: UserActionBroker):
        reset_hostname()


class ResetPrusaLink(ResetCheck):
    def __init__(self, *args, **kwargs):
        super().__init__(WizardCheckType.RESET_PRUSA_LINK, *args, **kwargs)

    def reset_task_run(self, actions: UserActionBroker):
        """
        Reset HTTP digest password for Prusa Link Web and
        Prusa Slicer. It will be regenerated on next boot.
        """
        Path(defines.http_digest_password_file).unlink(missing_ok=True)


class ResetPrusaConnect(ResetCheck):
    def __init__(self, *args, **kwargs):
        super().__init__(WizardCheckType.RESET_PRUSA_CONNECT, *args, **kwargs)

    def reset_task_run(self, actions: UserActionBroker):
        """
        Reset Prusa Connect registration. The file `prusa_printer_settings.ini` contains more info
        but for time being only Prusa Connect settings are
        being used.
        """
        Path(defines.prusa_printer_settings).unlink(missing_ok=True)


class ResetNetwork(ResetCheck):
    NETWORK_MANAGER = "org.freedesktop.NetworkManager"
    NM_SETTINGS_CONNECTION_FLAG_NM_GENERATED = 0x02

    def __init__(self, *args, **kwargs):
        super().__init__(WizardCheckType.RESET_NETWORK, *args, **kwargs)

    def reset_task_run(self, actions: UserActionBroker):
        system_bus = pydbus.SystemBus()
        for connection in system_bus.get(self.NETWORK_MANAGER, "Settings").ListConnections():
            try:
                con = system_bus.get(self.NETWORK_MANAGER, connection)
                if not con.Flags & self.NM_SETTINGS_CONNECTION_FLAG_NM_GENERATED:
                    con.Delete()
                else:
                    self._logger.debug("Not removing generated connection %s", connection)
            except GLib.GError:  # type: ignore[attr-defined]
                self._logger.exception("Failed to delete connection %s", connection)


class ResetTimezone(ResetCheck):
    def __init__(self, *args, **kwargs):
        super().__init__(WizardCheckType.RESET_TIMEZONE, *args, **kwargs)

    def reset_task_run(self, actions: UserActionBroker):
        Path(defines.local_time_path).unlink(missing_ok=True)
        copyfile(
            "/usr/share/factory/etc/localtime",
            "/etc/localtime",
            follow_symlinks=False,
        )


class ResetNTP(ResetCheck):
    def __init__(self, *args, **kwargs):
        super().__init__(WizardCheckType.RESET_NTP, *args, **kwargs)

    def reset_task_run(self, actions: UserActionBroker):
        pydbus.SystemBus().get("org.freedesktop.timedate1").SetNTP(True, False)


class ResetLocale(ResetCheck):
    def __init__(self, *args, **kwargs):
        super().__init__(WizardCheckType.RESET_LOCALE, *args, **kwargs)

    def reset_task_run(self, actions: UserActionBroker):
        pydbus.SystemBus().get("org.freedesktop.locale1").SetLocale(["C"], False)


class ResetUVCalibrationData(ResetCheck):
    def __init__(self, *args, **kwargs):
        super().__init__(WizardCheckType.RESET_UV_CALIBRATION_DATA, *args, **kwargs)

    def reset_task_run(self, actions: UserActionBroker):
        for name in UVCalibrationWizard.get_alt_names():
            (defines.configDir / name).unlink(missing_ok=True)


class RemoveSlicerProfiles(ResetCheck):
    def __init__(self, *args, **kwargs):
        super().__init__(WizardCheckType.REMOVE_SLICER_PROFILES, *args, **kwargs)

    def reset_task_run(self, actions: UserActionBroker):
        Path(defines.slicerProfilesFile).unlink(missing_ok=True)


class ResetHWConfig(ResetCheck):
    def __init__(self, package: WizardDataPackage, *args, disable_unboxing: bool = False, **kwargs):
        super().__init__(WizardCheckType.RESET_HW_CONFIG, *args, **kwargs)
        self._hw = package.hw
        self._disable_unboxing = disable_unboxing

    def reset_task_run(self, actions: UserActionBroker):
        self._hw.config.read_file()
        self._hw.config.factory_reset()
        if self._disable_unboxing:
            self._hw.config.showUnboxing = False
        self._hw.config.vatRevision = self._hw.printer_model.options.vat_revision  # type: ignore[attr-defined]
        self._hw.config.write()
        # TODO: Why is this here? Separate task would be better.
        rmtree(defines.wizardHistoryPath, ignore_errors=True)


class EraseMCEeprom(ResetCheck):
    def __init__(self, package: WizardDataPackage, *args, **kwargs):
        super().__init__(WizardCheckType.ERASE_MC_EEPROM, Configuration(None, None), [Resource.MC], *args, **kwargs)
        self._hw = package.hw

    def reset_task_run(self, actions: UserActionBroker):
        self._hw.eraseEeprom()


class ResetMovingProfiles(ResetCheck):
    """
    Set moving profiles to factory defaults
    """

    def __init__(self, package: WizardDataPackage, *args, **kwargs):
        super().__init__(WizardCheckType.RESET_MOVING_PROFILES,
                         Configuration(None, None),
                         [Resource.MC],
                         *args,
                         **kwargs)
        self._package = package

    def reset_task_run(self, actions: UserActionBroker):
        tower = self._package.hw.tower
        tower.profiles.factory_reset(True)
        tower.profiles.write()
        tower.set_stepper_sensitivity(0)
        tower.apply_all_profiles()
        tilt = self._package.hw.tilt
        tilt.profiles.factory_reset(True)
        tilt.profiles.write()
        tilt.set_stepper_sensitivity(0)
        tilt.apply_all_profiles()


class DisableFactory(SyncCheck):
    def __init__(self):
        super().__init__(WizardCheckType.DISABLE_FACTORY)

    def task_run(self, actions: UserActionBroker):
        self._logger.info("Factory reset - disabling factory mode")
        with FactoryMountedRW():
            defines.factory_enable.unlink(missing_ok=True)


class SendPrinterData(SyncCheck):
    def __init__(self, package: WizardDataPackage):
        super().__init__(WizardCheckType.SEND_PRINTER_DATA)
        self._hw = package.hw

    def task_run(self, actions: UserActionBroker):
        # pylint: disable = too-many-branches
        printer_model = self._hw.printer_model
        # Ensure some UV PWM is set, this ensure SL1 was UV calibrated
        if self._hw.config.uvPwm == 0:
            self._logger.error("Cannot do factory reset UV PWM not set (== 0)")
            raise MissingUVPWM()

        # Ensure the printer is able to compute UV PWM
        if printer_model.options.has_UV_calculation:  # type: ignore[attr-defined]
            compute_uvpwm(self._hw)

        # Ensure examples are present
        if not get_all_supported_files(printer_model, Path(defines.internalProjectPath)):
            raise MissingExamples()

        # Get wizard data
        try:
            with (defines.factoryMountPoint / SelfTestWizard.get_data_filename()).open("rt") as file:
                wizard_dict = json.load(file)
            if not wizard_dict and not self._hw.isKit:
                raise ValueError("Wizard data dictionary is empty")
            if self._hw.config.showWizard:
                raise Exception("Wizard data exists, but wizard is not considered done")
        except Exception as exception:
            raise MissingWizardData from exception

        if not self._hw.config.calibrated and not self._hw.isKit:
            raise MissingCalibrationData()

        # Get UV calibration data
        calibration_dict = {}
        # only for printers with UV calibration
        if printer_model.options.has_UV_calibration:  # type: ignore[attr-defined]
            try:
                with (defines.factoryMountPoint / UVCalibrationWizard.get_data_filename()).open("rt") as file:
                    calibration_dict = json.load(file)
                if not calibration_dict:
                    raise ValueError("UV Calibration dictionary is empty")
            except Exception as exception:
                raise MissingUVCalibrationData() from exception

        # Compose data to single dict, ensure basic data are present
        mqtt_data = {
            "osVersion": self._hw.system_version,
            "a64SerialNo": self._hw.cpuSerialNo,
            "mcSerialNo": self._hw.mcSerialNo,
            "mcFwVersion": self._hw.mcFwVersion,
            "mcBoardRev": self._hw.mcBoardRevision,
        }
        mqtt_data.update(wizard_dict)
        mqtt_data.update(calibration_dict)

        # Send data to MQTT
        topic = "prusa/sl1/factoryConfig"
        self._logger.info("Sending mqtt data: %s", mqtt_data)
        try:
            if not test_runtime.testing:
                mqtt.single(topic, json.dumps(mqtt_data), qos=2, retain=True, hostname=defines.mqtt_prusa_host)
            else:
                self._logger.debug("Testing mode, not sending MQTT data")
        except Exception as exception:
            self._logger.error("mqtt message not delivered. %s", exception)
            raise ErrorSendingDataToMQTT() from exception


class InitiatePackingMoves(DangerousCheck):
    def __init__(self, package: WizardDataPackage):
        super().__init__(package, WizardCheckType.INITIATE_PACKING_MOVES)

    async def async_task_run(self, actions: UserActionBroker):
        hw = self._package.hw
        await gather(hw.tower.verify_async(), hw.tilt.verify_async())

        # move tilt and tower to packing position
        hw.tilt.actual_profile = hw.tilt.profiles.homingFast
        hw.tilt.move(hw.config.tiltHeight)
        await hw.tilt.wait_to_stop_async()

        hw.tower.actual_profile = hw.tower.profiles.homingFast
        # TODO: Constant in code !!!
        await hw.tower.move_ensure_async(hw.config.tower_height_nm - Nm(74_000_000))


class FinishPackingMoves(Check):
    def __init__(self, package: WizardDataPackage):
        super().__init__(WizardCheckType.FINISH_PACKING_MOVES)
        self._hw = package.hw

    async def async_task_run(self, actions: UserActionBroker):
        # slightly press the foam against printers base
        # TODO: Constant in code !!!
        await self._hw.tower.move_ensure_async(self._hw.config.tower_height_nm - Nm(93_000_000))


class DisableAccess(SyncCheck):
    def __init__(self):
        super().__init__(WizardCheckType.DISABLE_ACCESS)

    def task_run(self, actions: UserActionBroker):
        with FactoryMountedRW():
            defines.ssh_service_enabled.unlink(missing_ok=True)
            defines.serial_service_enabled.unlink(missing_ok=True)


class ResetTouchUI(ResetCheck):
    TOUCH_UI_CONFIG = Path("/etc/touch-ui/touch-ui.conf")
    BACKLIGHT_STATE = Path("/var/lib/systemd/backlight/platform-backlight:backlight:backlight")
    SYSTEMD_INTERFACE = "org.freedesktop.systemd1"
    SYSTEMD_JOB_INTERFACE = "org.freedesktop.systemd1.Job"
    SYSTEMD_BACKLIGHT = "systemd-backlight@backlight:backlight.service"

    def __init__(self):
        super().__init__(WizardCheckType.RESET_TOUCH_UI)

    def reset_task_run(self, actions: UserActionBroker):
        self.TOUCH_UI_CONFIG.unlink(missing_ok=True)

        # Resetting the backlight state is a bit tricky
        # The backlight service will store the state on stop (usually system shutdown).
        # This removes the state file, stops the service and waits for the file to appear again.
        # Once the file appears it is removed again. This way we can be sure the service will
        # not recreate the file once we remove it.
        self.BACKLIGHT_STATE.unlink(missing_ok=True)
        self._restart_backlight_service()
        for _ in range(100):
            if self.BACKLIGHT_STATE.exists():
                break
            time.sleep(0.1)
        self.BACKLIGHT_STATE.unlink(missing_ok=True)

    def _restart_backlight_service(self):
        pydbus.SystemBus().get(self.SYSTEMD_INTERFACE).StopUnit(self.SYSTEMD_BACKLIGHT, "replace")

class ResetUpdateChannel(ResetCheck):
    """
    Set update channel to stable
    """

    def __init__(self, *args, **kwargs):
        super().__init__(WizardCheckType.RESET_UPDATE_CHANNEL, *args, **kwargs)

    def reset_task_run(self, actions: UserActionBroker):
        set_update_channel(channel="stable")
