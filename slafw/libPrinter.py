# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2021-2024 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import hashlib
import json
import logging
import os
import re
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from time import monotonic
from typing import Optional, Set, Any, Dict

from PySignal import Signal
from pydbus import SystemBus
from slafw.hardware.hardware import BaseHardware

from slafw import defines
from slafw.api.config0 import Config0
from slafw.api.devices import HardwareDeviceId
from slafw.api.logs0 import Logs0
from slafw.configs.hw import HwConfig
from slafw.configs.runtime import RuntimeConfig
from slafw.configs.stats import TomlConfigStats, TomlConfigStatsException
from slafw.errors import tests
from slafw.errors.errors import (
    NotUVCalibrated,
    NotMechanicallyCalibrated,
    BootedInAlternativeSlot,
    NoFactoryUvCalib,
    ConfigException,
    MotionControllerWrongFw,
    MotionControllerNotResponding,
    MotionControllerWrongResponse,
    UVPWMComputationError,
    OldExpoPanel,
    UvTempSensorFailed,
    PrinterException, FanFailed,
)
from slafw.functions.files import save_all_remain_wizard_history, get_all_supported_files
from slafw.functions.miscellaneous import toBase32hex
from slafw.functions.system import (
    get_configured_printer_model,
    set_configured_printer_model,
    set_factory_uvpwm,
    FactoryMountedRW,
    reset_hostname,
    compute_uvpwm,
    shut_down,
)
from slafw.hardware.sl1.hardware import HardwareSL1
from slafw.hardware.printer_model import PrinterModel
from slafw.image.exposure_image import ExposureImage
from slafw.libAsync import AdminCheck
from slafw.libAsync import SlicerProfileUpdater
from slafw.libNetwork import Network
from slafw.slicer.slicer_profile import SlicerProfile
from slafw.state_actions.manager import ActionManager
from slafw.states.exposure import ExposureState
from slafw.states.printer import PrinterState
from slafw.states.wizard import WizardState
from slafw.wizard.data_package import fill_wizard_data_package
from slafw.wizard.wizards.calibration import CalibrationWizard
from slafw.wizard.wizards.new_expo_panel import NewExpoPanelWizard
from slafw.wizard.wizards.self_test import SelfTestWizard
from slafw.wizard.wizards.sl1s_upgrade import SL1SUpgradeWizard, SL1DowngradeWizard
from slafw.wizard.wizards.unboxing import CompleteUnboxingWizard, KitUnboxingWizard
from slafw.wizard.wizards.uv_calibration import UVCalibrationWizard
from slafw.exposure.persistence import ExposurePickler


class Printer:
    # pylint: disable = too-many-instance-attributes
    # pylint: disable = too-many-public-methods
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Printer initializing")
        self._printer_identifier: Optional[str] = None
        init_time = monotonic()
        self.exception_occurred = Signal()  # Use this one to emit recoverable errors
        self.fatal_error: Optional[Exception] = None
        self.fatal_error_changed = Signal()
        self.admin_check: Optional[AdminCheck] = None
        self.slicer_profile: Optional[SlicerProfile] = None
        self.slicer_profile_updater: Optional[SlicerProfileUpdater] = None
        self.state_changed = Signal()
        self.http_digest_password_changed = Signal()
        self.data_privacy_changed = Signal()
        self.action_manager: ActionManager = ActionManager()
        self.action_manager.exposure_changed.connect(self._on_exposure_changed)
        self.action_manager.exposure_data_changed.connect(self._on_exposure_data_changed)
        self.action_manager.wizard_state_changed.connect(self._on_wizard_state_changed)
        self._states: Set[PrinterState] = {PrinterState.INIT}
        self._dbus_subscriptions = []
        self.unboxed_changed = Signal()
        self.mechanically_calibrated_changed = Signal()
        self.uv_calibrated_changed = Signal()
        self.self_tested_changed = Signal()
        self._oneclick_inhibitors: Set[str] = set()
        self._run_expo_panel_wizard = False

        # HwConfig and runtime config
        self.hw_config = HwConfig(
            file_path=Path(defines.hwConfigPath),
            factory_file_path=Path(defines.hwConfigPathFactory),
            is_master=True,
        )

        self.hw_config.add_onchange_handler(self._config_changed)
        self.runtime_config = RuntimeConfig()
        try:
            self.hw_config.read_file()
        except ConfigException:
            self.logger.warning("Failed to read configuration file", exc_info=True)
        self.logger.info(str(self.hw_config))

        self._system_bus = SystemBus()
        self.inet: Optional[Network] = None
        self.exposure_image: Optional[ExposureImage] = None
        self.config0_dbus = None
        self.logs0_dbus = None
        self.hw: Optional[BaseHardware] = None
        self.exposure_pickler: Optional[ExposurePickler] = None

        self.logger.info("Printer initialized in %.03f seconds", monotonic() - init_time)

    @property
    def state(self) -> PrinterState:
        return PrinterState.get_most_important(self._states)

    def set_state(self, state: PrinterState, active: bool = True):
        old = self.state
        if active:
            self._states.add(state)
        elif state in self._states:
            self._states.remove(state)
        if old != self.state:
            self.logger.info("Printer state changed: %s -> %s", old, self.state)
            self.state_changed.emit()

    def has_state(self, state: PrinterState) -> bool:
        return state in self._states

    def enter_fatal_error(self, exception: Exception):
        self.set_state(PrinterState.EXCEPTION)
        self.fatal_error = exception
        self.fatal_error_changed.emit(self.fatal_error)

    def setup(self):
        try:
            self.do_setup()
        except Exception as exception:
            self.logger.exception("Printer setup failure")
            self.enter_fatal_error(exception)

    def do_setup(self):
        # pylint: disable = too-many-statements
        self.logger.info("Printer starting, PID: %d", os.getpid())
        start_time = monotonic()

        self.logger.info("Initializing libHardware")
        self.hw = HardwareSL1(self.hw_config, PrinterModel())
        self.logger.info("System version: %s", self.hw.system_version)

        self.hw.uv_led_temp.overheat_changed.connect(self._on_uv_led_temp_overheat)
        self.hw.uv_led_fan.error_changed.connect(self._on_uv_fan_error)
        self.hw.blower_fan.error_changed.connect(self._on_blower_fan_error)
        self.hw.rear_fan.error_changed.connect(self._on_rear_fan_error)

        # needed before init of other components (display etc)
        # TODO: Enable this once kit A64 do not require being turned on during manufacturing.
        #   Currently calibration needs to be performed in the factory.
        # if self.factoryMode and self.hw.isKit:
        #     self.factoryMode = False
        #     self.logger.warning("Factory mode disabled for kit")
        #

        self.inet = Network(self.hw.cpuSerialNo, self.hw.system_version)
        self.exposure_image = ExposureImage(self.hw)

        self.logger.info("Registering remaining D-Bus services")
        self.config0_dbus = self._system_bus.publish(Config0.__INTERFACE__, Config0(self.hw_config))
        self.logs0_dbus = self._system_bus.publish(Logs0.__INTERFACE__, Logs0(self.hw))

        try:
            TomlConfigStats(defines.statsData, self.hw).update_reboot_counter()
        except TomlConfigStatsException:
            self.logger.exception("Error when update 'system_up_since' statistics.")

        self._connect_hw()
        self._register_event_handlers()

        # Factory mode and admin
        self.runtime_config.factory_mode = defines.factory_enable.exists()
        self.logger.info("Factory mode: %s", self.runtime_config.factory_mode)
        self.runtime_config.show_admin = self.runtime_config.factory_mode
        if not self.runtime_config.factory_mode:
            self.admin_check = AdminCheck(self.runtime_config, self.hw, self.inet)

        self._load_slicer_profiles()

        # Force update network state (in case we missed network going online)
        # All network state handler should be already registered
        self.inet.force_refresh_state()

        if self.hw.checkFailedBoot():
            self.exception_occurred.emit(BootedInAlternativeSlot())

        # Model detection
        self._firstboot()
        if self.hw.printer_model == PrinterModel.SL1 and not defines.printer_model.exists():
            set_configured_printer_model(self.hw.printer_model)  # Configure model for old SL1 printers

        # UV calibration
        if not self.hw.config.is_factory_read() and not self.hw.isKit and self.hw.printer_model == PrinterModel.SL1:
            self.exception_occurred.emit(NoFactoryUvCalib())
        self._compute_uv_pwm()

        # Past exposures
        save_all_remain_wizard_history()
        self.exposure_pickler = ExposurePickler(fill_wizard_data_package(self))
        self.action_manager.load_exposure(self.exposure_pickler)

        # Set the default exposure for tank cleaning
        if not self.hw.config.tankCleaningExposureTime:
            if self.hw.printer_model == PrinterModel.SL1:
                self.hw.config.tankCleaningExposureTime = 50  # seconds
            else:
                self.hw.config.tankCleaningExposureTime = 30  # seconds
            self.hw.config.write()

        # Finish setup
        self.logger.info("Printer started in %.03f seconds", monotonic() - start_time)

    def stop(self):
        self.action_manager.exit()
        if self.exposure_image:
            self.exposure_image.exit()
        if self.hw:
            self.hw.exit()
        if self.config0_dbus:
            self.config0_dbus.unpublish()
        if self.logs0_dbus:
            self.logs0_dbus.unpublish()
        for subscription in self._dbus_subscriptions:
            subscription.unsubscribe()

    def _connect_hw(self):
        self.logger.info("Connecting to hardware components")
        try:
            self.hw.connect()
        except (MotionControllerWrongFw, MotionControllerNotResponding,
                MotionControllerWrongResponse):
            # Log this as info, this is usually not an error. Show exec info to enable debugging this actually
            # is an error (flashing in a loop, broken MC).
            self.logger.info("HW connect failed with a recoverable error, flashing MC firmware", exc_info=True)
            self.set_state(PrinterState.UPDATING_MC)
            self.hw.flashMC()
            self.hw.connect()
            self.hw.eraseEeprom()
            self.set_state(PrinterState.UPDATING_MC, active=False)

        self.logger.info("Starting libHardware")
        self.hw.start()
        self.logger.info("Starting ExposureImage")
        self.exposure_image.start()
        self.hw.uv_led.off()
        self.hw.power_led.reset()

    def _register_event_handlers(self):
        self.logger.info("Registering event handlers")
        self.inet.register_events()
        self._dbus_subscriptions.append(
            self._system_bus.get("de.pengutronix.rauc", "/").PropertiesChanged.connect(self._rauc_changed)
        )
        self.logger.info("connecting cz.prusa3d.sl1.filemanager0 DBus signals")
        self._dbus_subscriptions.append(
            self._system_bus.subscribe(
                object="/cz/prusa3d/sl1/filemanager0", signal="OneClickPrintFile", signal_fired=self._one_click_file
            )
        )
        self._dbus_subscriptions.append(
            self._system_bus.get("cz.prusa3d.sl1.filemanager0").PropertiesChanged.connect(self._filemanager_properties_changed
            )
        )

    def _load_slicer_profiles(self):
        self.logger.info("Loading slicer profiles")
        self.slicer_profile = SlicerProfile(defines.slicerProfilesFile)
        if not self.slicer_profile.load():
            self.logger.debug("Trying bundled slicer profiles")
            self.slicer_profile = SlicerProfile(defines.slicerProfilesFallback)
            if not self.slicer_profile.load():
                self.logger.error("No suitable slicer profiles found")

        if self.slicer_profile.vendor:
            self.logger.info("Starting slicer profiles updater")
            self.slicer_profile_updater = SlicerProfileUpdater(
                self.inet, self.slicer_profile, self.hw.printer_model.name
            )

    def _firstboot(self):
        # This is supposed to run on new printers /run/firstboot file is provided by a service configured to run
        # on the firstboot. The firmware does not know whether the printer has been manufactured as SL1 or SL1S it
        # has to detect its initial HW configuration on first start.
        # M1 is detected as SL1S and switched in admin
        if not defines.firstboot.exists():
            return

        self.hw.config.vatRevision = self.hw.printer_model.options.vat_revision
        if self.hw.printer_model == PrinterModel.SL1S:
            set_factory_uvpwm(self.hw.uv_led.parameters.safe_default_pwm)
            incompatible_extension = PrinterModel.SL1
        else:
            incompatible_extension = PrinterModel.SL1S

        # Force remove incompatible projects on firstboot
        files_to_remove = get_all_supported_files(incompatible_extension, Path(defines.internalProjectPath))
        for file in files_to_remove:
            self.logger.info("Removing incompatible example project: %s", file)
            os.remove(file)
        set_configured_printer_model(self.hw.printer_model)

    def _model_update(self):
        config_model = get_configured_printer_model()
        if self.hw.printer_model is not config_model:
            self.logger.info('Printer model change detected from "%s" to "%s"',
                             config_model.name, self.hw.printer_model.name)
            if self.hw.printer_model == PrinterModel.SL1S:
                upgrade = self.action_manager.start_wizard(SL1SUpgradeWizard(fill_wizard_data_package(self)))
            elif self.hw.printer_model == PrinterModel.SL1:
                upgrade = self.action_manager.start_wizard(SL1DowngradeWizard(fill_wizard_data_package(self)))
            self.set_state(PrinterState.WIZARD, active=True)
            upgrade.join()
            try:
                reset_hostname()  # set model specific default hostname
            except PrinterException:
                self.logger.exception("Failed to reset hostname after model ")

    def _compute_uv_pwm(self):
        if not self.hw.printer_model.options.has_UV_calculation:
            self.logger.debug("Not computing UV PWM as printer model does not support UV calculation")
            return

        self._detect_new_expo_panel()
        try:
            pwm = compute_uvpwm(self.hw)
            self.hw.config.uvPwm = pwm
            self.logger.info("Computed UV PWM: %s", pwm)
        except UVPWMComputationError:
            self.logger.exception("Failed to compute UV PWM")
            self.hw.config.uvPwm = self.hw.uv_led.parameters.safe_default_pwm

    def _rauc_changed(self, __, changed, ___):
        if "Operation" in changed:
            self.set_state(PrinterState.UPDATING, changed["Operation"] != "idle")

    def _on_exposure_changed(self):
        exposure = self.action_manager.exposure
        self.set_state(PrinterState.PRINTING, exposure and not exposure.done)

    def _on_exposure_data_changed(self, key: str, value: Any):
        self.logger.debug("on_exposure_data_changed: %s set to %s", key, value)
        if key == "state":
            self.set_state(PrinterState.PRINTING, value not in ExposureState.finished_states())
            # save & power off
            if self.hw.config.autoOff and value == ExposureState.FINISHED:
                self.exposure_pickler.save(self.action_manager.exposure)
                shut_down(self.hw)

    def _on_wizard_state_changed(self, state: WizardState):
        self.set_state(PrinterState.WIZARD, state not in WizardState.finished_states())

    @property
    def id(self) -> str:
        """Return a hex string identification for the printer image."""

        if self._printer_identifier is None:
            boot = 1
            output = subprocess.check_output("lsblk -l | grep -e '/$' | awk '{print $1}'", shell=True)
            slot = output.decode().strip()
            if slot not in ["mmcblk2p2", "mmcblk2p3"]:
                boot = 0

            mac_eth0 = self.inet.get_eth_mac()
            cpu_serial = self.hw.cpuSerialNo.strip(" *")
            emmc_serial = self.hw.emmc_serial
            trusted_image = 0

            hash_hex = hashlib.sha256((emmc_serial + mac_eth0 + cpu_serial).encode()).hexdigest()
            binary = str(trusted_image) + str(boot) + bin(int(hash_hex[:10], 16))[2:-2]
            self._printer_identifier = toBase32hex(int(binary, 2))

        return self._printer_identifier

    @property
    def http_digest_password(self) -> str:
        """
        Get current HTTP digest password in plaintext

        :return: Current HTTP digest password string
        """
        try:
            return defines.http_digest_password_file.read_text(encoding="utf-8")
        except IOError as e:
            raise ConfigException("Digest auth file read failed") from e

    @http_digest_password.setter
    def http_digest_password(self, password: str) -> None:
        subprocess.check_call(["/bin/htdigest-keygen.sh", password])
        self.http_digest_password_changed.emit()

    @property
    def data_privacy(self) -> bool:
        return self.hw.config.data_privacy

    @data_privacy.setter
    def data_privacy(self, enabled: bool) -> None:
        self.hw.config.data_privacy = enabled
        self.hw.config.write()
        self.data_privacy_changed.emit()

    @property
    def help_page_url(self) -> str:
        url = ""
        if self.data_privacy:
            fw_version = re.sub(r"([\.\d]*)[^\.\d].*", r"\g<1>", self.hw.system_version)
            url += f"/{self.id}/{fw_version}"

        return url

    def _one_click_file(self, _, __, ___, ____, params):
        if self._oneclick_inhibitors:
            self.logger.info("Oneclick inhibited by: %s", self._oneclick_inhibitors)
            return

        try:
            path = params[0]
            if path and os.path.isfile(path):
                self.logger.info("Opening project %s", path)
                last_exposure = self.action_manager.exposure
                if last_exposure:
                    last_exposure.try_cancel()
                self.action_manager.new_exposure(self.exposure_pickler, path)
        except (NotUVCalibrated, NotMechanicallyCalibrated):
            self.run_make_ready_to_print()
        except Exception:
            self.logger.exception("Error handling one click file event")
            raise

    def _filemanager_properties_changed(self, interface: str, changed: Dict, invalidated: Dict):
        if invalidated:
            self.logger.warning("%s invalidated properties: %s", interface, invalidated)
        if "media_mounted" in changed and changed["media_mounted"] is False:
            # If the currently printed project(exposure) is on the unmounted media, cancel it.
            try:
                self.logger.info("Media mounted: %s", changed["media_mounted"])
                expo = self.action_manager.exposure
                if expo and expo.project and not Path(expo.project.data.path).exists():
                    expo.try_cancel()
            except Exception:
                self.logger.exception("Error handling media unmounted event")
                try:
                    expo = self.action_manager.exposure
                    expo.try_cancel()
                except Exception:
                    self.logger.exception("Exposure couldn't be canceled")

    def add_oneclick_inhibitor(self, name: str):
        if name in self._oneclick_inhibitors:
            self.logger.warning("One click inhibitor %s already registered", name)
            return

        self._oneclick_inhibitors.add(name)

    def remove_oneclick_inhibitor(self, name: str):
        if name in self._oneclick_inhibitors:
            self._oneclick_inhibitors.remove(name)
        else:
            self.logger.warning("One click inhibitor %s not registered", name)

    @property
    def unboxed(self):
        return not self.hw.config.showUnboxing

    @property
    def mechanically_calibrated(self):
        return self.hw.config.calibrated

    @property
    def uv_calibrated(self):
        return self.hw.config.uvPwm >= self.hw.uv_led.parameters.min_pwm

    @property
    def self_tested(self):
        return not self.hw.config.showWizard

    @property
    def is_calibrated(self):
        return self.mechanically_calibrated and self.uv_calibrated and self.self_tested

    def check_printer_calibrated_before_print(self):
        """
        Make sure that the printer is calibrated before print
        """
        if not self.is_calibrated:
            if not self.uv_calibrated:
                raise NotUVCalibrated()
            raise NotMechanicallyCalibrated()

    def run_make_ready_to_print(self):
        threading.Thread(target=self._make_ready_to_print, daemon=True).start()

    def _make_ready_to_print(self):
        self._model_update()
        passing = True
        if not self.runtime_config.factory_mode and self.hw.config.showUnboxing:
            if self.hw.isKit:
                unboxing = self.action_manager.start_wizard(
                    KitUnboxingWizard(fill_wizard_data_package(self)), handle_state_transitions=False
                )
            else:
                unboxing = self.action_manager.start_wizard(
                    CompleteUnboxingWizard(fill_wizard_data_package(self)), handle_state_transitions=False
                )
            self.logger.info("Running unboxing wizard")
            self.set_state(PrinterState.WIZARD, active=True)
            unboxing.join()
            passing = unboxing.state is WizardState.DONE
            self.logger.info("Unboxing wizard finished")

        if self._run_expo_panel_wizard and passing:
            self.logger.info("Running new expo panel wizard")
            new_expo_panel_wizard = self.action_manager.start_wizard(
                NewExpoPanelWizard(fill_wizard_data_package(self)), handle_state_transitions=False
            )
            self.set_state(PrinterState.WIZARD, active=True)
            new_expo_panel_wizard.join()
            passing = new_expo_panel_wizard.state is WizardState.DONE
            self.logger.info("New expo panel wizard finished")

        if self.hw.config.showWizard and passing:
            self.logger.info("Running selftest wizard")
            selftest = self.action_manager.start_wizard(
                SelfTestWizard(fill_wizard_data_package(self)), handle_state_transitions=False
            )
            self.set_state(PrinterState.WIZARD, active=True)
            selftest.join()
            passing = selftest.state is WizardState.DONE
            self.logger.info("Selftest wizard finished")

        if not self.hw.config.calibrated and passing:
            self.logger.info("Running calibration wizard")
            calibration = self.action_manager.start_wizard(
                CalibrationWizard(fill_wizard_data_package(self)), handle_state_transitions=False
            )
            self.set_state(PrinterState.WIZARD, active=True)
            calibration.join()
            passing = calibration.state is WizardState.DONE
            self.logger.info("Calibration wizard finished")

        if not self.uv_calibrated and passing:
            # delete also both counters and save calibration to factory partition. It's new KIT or something went wrong.
            self.logger.info("Running UV calibration wizard")
            uv_calibration = self.action_manager.start_wizard(
                UVCalibrationWizard(fill_wizard_data_package(self), display_replaced=True, led_module_replaced=True),
                handle_state_transitions=False,
            )
            self.set_state(PrinterState.WIZARD, active=True)
            uv_calibration.join()
            self.logger.info("UV calibration wizard finished")

        self.set_state(PrinterState.WIZARD, active=False)
        self.set_state(PrinterState.RUNNING)

    def inject_exception(self, code: str):
        exception = tests.get_instance_by_code(code)
        self.logger.info("Injecting exception %s", exception)
        self.exception_occurred.emit(exception)

    def _config_changed(self, key: str, _: Any):
        if key.lower() == "showunboxing":
            self.unboxed_changed.emit()
            return

        if key.lower() == "showwizard":
            self.self_tested_changed.emit()
            return

        if key.lower() == "calibrated":
            self.mechanically_calibrated_changed.emit()
            return

        if key.lower() == "uvpwm":
            self.uv_calibrated_changed.emit()
            return

    def _detect_new_expo_panel(self):
        panel_sn = self.hw.exposure_screen.serial_number
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(defines.expoPanelLogPath, "r", encoding="utf-8") as f:
                log = json.load(f)
            last_key = list(log)[-1]
            if log[last_key]["panel_sn"] != panel_sn:  # if new panel detected
                for record in log.values():  # check if panel was already used in this printer
                    if record["panel_sn"] == panel_sn and "counter_s" in record.keys():
                        self.exception_occurred.emit(
                            OldExpoPanel(counter_h=round(record["counter_s"] / 3600))
                        )  # show warning about used panel
                self._run_expo_panel_wizard = True
                # Force selftest and calibration with new display as:
                # - Printer internals might have been tempered with
                # - Display plane might have shifted
                self.hw.config.showWizard = True
                self.hw.config.calibrated = False
                self.hw.config.write()

        except Exception as e:  # no records found
            self.logger.exception(e)
            with FactoryMountedRW():
                with open(defines.expoPanelLogPath, "a+", encoding="utf-8") as f:
                    f.seek(0)
                    self.logger.warning("Expo panel logs: Current contents: %s", f.read())
                    record = {timestamp: {"panel_sn": panel_sn}}
                    f.seek(0)
                    f.truncate()
                    self.logger.warning("Expo panel logs: Adding first record: %s", panel_sn)
                    json.dump(record, f, indent=2)

    def _on_uv_led_temp_overheat(self, overheated: bool):
        if not overheated:
            self.hw.power_led.remove_error()
            self.set_state(PrinterState.OVERHEATED, False)
        else:
            self.logger.error("UV LED overheated")
            self.hw.power_led.set_error()
            if not self.has_state(PrinterState.PRINTING):
                self.hw.uv_led.off()
            self.set_state(PrinterState.OVERHEATED, True)

            if self.hw.uv_led_temp.value < 0:
                # TODO: Raise an exception instead of negative value
                self.logger.error("UV temperature reading failed")
                self.hw.uv_led.off()
                self.exception_occurred.emit(UvTempSensorFailed())

    def _on_uv_fan_error(self, error: bool):
        if not self.has_state(PrinterState.PRINTING) and error:
            self.exception_occurred.emit(FanFailed(HardwareDeviceId.UV_LED_FAN.value))

    def _on_blower_fan_error(self, error: bool):
        if not self.has_state(PrinterState.PRINTING) and error:
            self.exception_occurred.emit(FanFailed(HardwareDeviceId.BLOWER_FAN.value))

    def _on_rear_fan_error(self, error: bool):
        if not self.has_state(PrinterState.PRINTING) and error:
            self.exception_occurred.emit(FanFailed(HardwareDeviceId.REAR_FAN.value))

    def hw_all_off(self):
        self.exposure_image.blank_screen()
        self.hw.uv_led.off()
        self.hw.stop_fans()
        self.hw.motors_release()
