# This file is part of the SLA firmware
# Copyright (C) 2020-2024 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio
import json
import unittest
from pathlib import Path
from shutil import copyfile
from tempfile import NamedTemporaryFile
from typing import Optional
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from dataclasses import dataclass
import time
import pydbus
import toml

from slafw.configs.unit import Nm, Ustep
from slafw.tests.mocks.hardware import HardwareMock
from slafw.wizard.wizards.new_expo_panel import NewExpoPanelWizard

from slafw import defines
from slafw.configs.hw import HwConfig
from slafw.configs.runtime import RuntimeConfig
from slafw.errors.errors import UVTooDimm, UVTooBright, UVDeviationTooHigh, TowerHomeFailed, TowerEndstopNotReached
from slafw.functions.system import get_configured_printer_model, set_configured_printer_model
from slafw.hardware.printer_model import PrinterModel
from slafw.states.wizard import WizardState, WizardId
from slafw.tests.base import SlafwTestCaseDBus
from slafw.tests.mocks.uv_meter import UVMeterMock
from slafw.wizard.actions import UserActionBroker
from slafw.wizard.checks.base import Check, WizardCheckType, WizardCheckState
from slafw.wizard.group import CheckGroup
from slafw.wizard.setup import Configuration, PlatformSetup, TankSetup
from slafw.wizard.wizard import Wizard
from slafw.wizard.wizard import serializer
from slafw.wizard.data_package import WizardDataPackage, make_config_writers
from slafw.wizard.wizards.calibration import CalibrationWizard
from slafw.wizard.wizards.displaytest import DisplayTestWizard
from slafw.wizard.wizards.factory_reset import FactoryResetWizard, PackingWizard
from slafw.wizard.wizards.self_test import SelfTestWizard
from slafw.wizard.wizards.sl1s_upgrade import SL1SUpgradeWizard
from slafw.wizard.wizards.unboxing import CompleteUnboxingWizard, KitUnboxingWizard
from slafw.wizard.wizards.uv_calibration import UVCalibrationWizard
from slafw.wizard.wizards.tank_surface_cleaner import TankSurfaceCleaner


@dataclass
class MockDataclass:
    first: Mock = Mock()
    second: Mock = Mock()


class TestGroup(CheckGroup):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_mock = AsyncMock()

    async def setup(self, actions: UserActionBroker):
        self.setup_mock(actions)


class TestWizardInfrastructure(SlafwTestCaseDBus):
    # pylint: disable=no-self-use

    def setUp(self) -> None:
        super().setUp()
        self.package = WizardDataPackage(Mock(), MockDataclass(), Mock())

    def test_wizard_group_run(self):
        group = AsyncMock()
        group.checks = []
        # group.setup.return_value = None

        wizard = Wizard(WizardId.SELF_TEST, [group], self.package)
        self.assertEqual(WizardState.INIT, wizard.state)
        wizard.start()
        wizard.join()

        self.assertEqual(WizardState.DONE, wizard.state)
        group.run.assert_called()
        group.run.assert_awaited()

    def test_wizard_failure(self):
        # pylint: disable = too-many-ancestors
        class Test(MagicMock, Check):
            async def async_task_run(self, actions: UserActionBroker):
                pass

            def __init__(self):
                MagicMock.__init__(self)
                Check.__init__(self, WizardCheckType.UNKNOWN, Mock(), [])

        check = Test()
        exception = Exception("Synthetic fail")
        task_body = AsyncMock()
        task_body.side_effect = exception
        check.async_task_run = task_body
        wizard = Wizard(WizardId.SELF_TEST, [TestGroup(Mock(), [check])], self.package)
        wizard.start()
        wizard.join()

        self.assertEqual(WizardState.FAILED, wizard.state)
        self.assertEqual(exception, wizard.exception)

    def test_wizard_warning(self):
        warning = Warning("Warning")

        class Test(Check):
            async def async_task_run(self, actions: UserActionBroker):
                self.add_warning(warning)

            def __init__(self):
                super().__init__(WizardCheckType.UNKNOWN, Mock(), [])

        check = Test()
        wizard = Wizard(WizardId.SELF_TEST, [TestGroup(Mock(), [check])], self.package)
        wizard.start()
        wizard.join()

        self.assertEqual(WizardState.DONE, wizard.state)
        self.assertIn(warning, wizard.warnings)

    def test_group_setup(self):
        test = TestGroup(Mock(), [])
        actions = Mock()
        asyncio.run(test.run(actions))
        test.setup_mock.assert_called()

    def test_check_execution(self):
        check = AsyncMock()
        actions = Mock()
        group = TestGroup(Mock(), [check])
        asyncio.run(group.run(actions))

        check.run.assert_called()

    def test_configuration_match(self):
        check = Mock()
        check.configuration = Configuration(TankSetup.UV, PlatformSetup.RESIN_TEST)

        with self.assertRaises(ValueError):
            TestGroup(Configuration(TankSetup.PRINT, PlatformSetup.PRINT), [check])

    def test_check_progress(self):
        class TestCheck(Check):
            async def async_task_run(self, actions: UserActionBroker):
                self.progress = 0.5

        check = TestCheck(WizardCheckType.UNKNOWN, Mock(), [])
        callback = Mock()
        callback.__name__ = "callback"
        check.data_changed.connect(lambda: callback(check.data["progress"]))

        asyncio.run(check.run(Mock(), Mock(), Mock()))

        callback.assert_any_call(0)
        callback.assert_any_call(0.5)
        callback.assert_any_call(1)


class TestWizardsBase(SlafwTestCaseDBus):
    def setUp(self) -> None:
        super().setUp()
        self.hw_config_file = self.TEMP_DIR / "reset_config.toml"
        self.hw_config_factory_file = self.TEMP_DIR / "reset_config_factory.toml"
        hw_config = HwConfig(self.hw_config_file, self.hw_config_factory_file, is_master=True)
        hw_config.tankCleaningExposureTime = 5  # Avoid waiting for long exposures
        self.hw = HardwareMock(hw_config, PrinterModel.SL1)
        self.package = WizardDataPackage(
                hw=self.hw,
                config_writers=make_config_writers(self.hw.config),
                runtime_config=RuntimeConfig(),
                exposure_image=Mock()
        )

    def _run_wizard(self, wizard: Wizard, limit_s: int = 5, expected_state=WizardState.DONE):
        wizard.start()
        wizard.join(limit_s)

        while wizard.is_alive() and wizard.state not in WizardState.finished_states():
            if wizard.state == WizardState.STOPPED:
                wizard.abort()
            else:
                try:
                    wizard.force_cancel()
                except RuntimeError:
                    pass  # Wizard might have reached stopped in the meantime

        wizard.join(limit_s * 3)
        self.assertFalse(wizard.is_alive())
        self.assertEqual(expected_state, wizard.state)


class TestDisplayTest(TestWizardsBase):
    def test_display_test(self):
        wizard = DisplayTestWizard(self.package)

        def on_state_changed(state):
            if state == WizardState.PREPARE_DISPLAY_TEST:
                wizard.prepare_displaytest_done()
            if state == WizardState.SHOW_RESULTS:
                wizard.show_results_done()
            if state == WizardState.TEST_DISPLAY:
                wizard.report_display(True)

        wizard.state_changed.connect(on_state_changed)
        self._run_wizard(wizard)

    def test_display_test_fail(self):
        wizard = DisplayTestWizard(self.package)

        def on_state_changed(state):
            if state == WizardState.PREPARE_DISPLAY_TEST:
                wizard.prepare_displaytest_done()
            if state == WizardState.TEST_DISPLAY:
                wizard.report_display(False)
            if state == WizardState.STOPPED:
                wizard.abort()
            if state == WizardState.SHOW_RESULTS:
                wizard.show_results_done()

        wizard.state_changed.connect(on_state_changed)
        self._run_wizard(wizard, expected_state=WizardState.FAILED)
        self.assertEqual("#10120", wizard.data["displaytest_exception"]["code"])


class TestUpgradeWizard(TestWizardsBase):
    def setUp(self) -> None:
        super().setUp()
        self.hw = HardwareMock(
            HwConfig(defines.hwConfigPath, defines.hwConfigPathFactory, is_master=True), PrinterModel.SL1S
        )
        self.package.hw = self.hw
        self.package.config_writers.hw_config = self.hw.config.get_writer()
        set_configured_printer_model(PrinterModel.SL1)

    def tearDown(self) -> None:
        del self.hw
        super().tearDown()

    def test_sl1s_upgrade_confirm(self):
        wizard = SL1SUpgradeWizard(self.package)

        def on_state_changed(state):
            if state == WizardState.SL1S_CONFIRM_UPGRADE:
                wizard.sl1s_confirm_upgrade()
            if state == WizardState.SHOW_RESULTS:
                wizard.show_results_done()

        wizard.state_changed.connect(on_state_changed)
        self._run_wizard(wizard)
        self.assertEqual(1, self.hw.config.vatRevision)
        self.assertEqual(PrinterModel.SL1S, get_configured_printer_model())
        config = HwConfig(defines.hwConfigPath, defines.hwConfigPathFactory)
        config.read_file()
        self.assertEqual(1, config.vatRevision)
        self.assertEqual(123, config.uvPwm)
        self.assertEqual(0, config.uvPwmTune)
        self.assertEqual(123, config.uvPwmPrint)
        self.assertEqual(123, config.get_values()["uvPwm"].get_factory_value(config))

    def test_sl1s_upgrade_reject(self):
        wizard = SL1SUpgradeWizard(self.package)

        def on_state_changed(state):
            if state == WizardState.SL1S_CONFIRM_UPGRADE:
                print("Rejecting upgrade")
                wizard.sl1s_reject_upgrade()
            if state == WizardState.CANCELED:
                print("aborting")
                wizard.abort()

        wizard.state_changed.connect(on_state_changed)
        self._run_wizard(wizard, expected_state=WizardState.CANCELED)
        self.assertEqual(0, self.hw.config.vatRevision)
        self.assertEqual(PrinterModel.SL1, get_configured_printer_model())


class TestWizards(TestWizardsBase):
    def setUp(self) -> None:
        super().setUp()
        set_configured_printer_model(PrinterModel.SL1)

        # Mock factory data
        self.hw.config.uvPwm = 210
        copyfile(
            self.SAMPLES_DIR / "uv_calibration_data.json",
            defines.factoryMountPoint / UVCalibrationWizard.get_data_filename(),
        )
        copyfile(
            self.SAMPLES_DIR / "self_test_data.json", defines.factoryMountPoint / SelfTestWizard.get_data_filename()
        )

        defines.expoPanelLogPath = self.TEMP_DIR / defines.expoPanelLogFileName
        copyfile(self.SAMPLES_DIR / defines.expoPanelLogFileName, defines.expoPanelLogPath)

        # Setup files that are touched by packing wizard
        defines.http_digest_password_file = self.TEMP_DIR / "api.key"
        defines.http_digest_password_file.touch()
        defines.local_time_path = self.TEMP_DIR / "localtime"
        defines.local_time_path.touch()
        defines.slicerProfilesFile = self.TEMP_DIR / "slicer_profiles"
        defines.slicerProfilesFile.touch()
        defines.internalProjectPath = self.TEMP_DIR / "projects"
        defines.internalProjectPath.mkdir()
        (defines.internalProjectPath / "dummy_project.sl1").touch()
        defines.prusa_printer_settings = self.TEMP_DIR / "remote_config"
        defines.prusa_printer_settings.write_text("DUMMY TEXT")
        defines.factory_enable = self.TEMP_DIR / "factory"
        defines.factory_enable.touch()
        defines.serial_service_enabled = self.TEMP_DIR / "serial"
        defines.serial_service_enabled.touch()
        defines.ssh_service_enabled = self.TEMP_DIR / "ssh"
        defines.ssh_service_enabled.touch()

        # Mock changed settings
        self.time_date.SetNTP(not self.time_date.DEFAULT_NTP, False)
        self.time_date.SetTimezone("Europe/Prague", False)
        self.locale.SetLocale("en_US.utf-8", False)
        self.touch_ui_config = Path(NamedTemporaryFile(delete=False).name)  # pylint: disable = consider-using-with
        self.backlight_state = Path(NamedTemporaryFile(delete=False).name)  # pylint: disable = consider-using-with

    def tearDown(self) -> None:
        del self.hw
        self.touch_ui_config.unlink(missing_ok=True)
        self.backlight_state.unlink(missing_ok=True)
        super().tearDown()

    def _run_wizard(self, wizard: Wizard, limit_s: int = 5, expected_state=WizardState.DONE):
        with (
            patch("slafw.wizard.checks.factory_reset.copyfile"),
            patch("slafw.wizard.checks.factory_reset.ch_mode_owner"),
            patch("slafw.wizard.checks.factory_reset.ResetTouchUI.BACKLIGHT_STATE", self.backlight_state),
            patch(
                "slafw.wizard.checks.factory_reset.ResetTouchUI._restart_backlight_service",
                self.backlight_state.touch
            ),
            patch("slafw.wizard.checks.factory_reset.ResetTouchUI.TOUCH_UI_CONFIG", self.touch_ui_config),
            patch("slafw.wizard.checks.factory_reset.set_update_channel")
        ):
            super()._run_wizard(wizard, limit_s, expected_state)

    def _run_self_test(self, expected_state=WizardState.DONE) -> dict:
        self.hw.config.uvWarmUpTime = 2
        original_move = self.hw.tower.move

        def side_effect_move(position):
            if position == self.hw.tower.max_nm:
                original_move(self.hw.tower.end_nm)
            else:
                original_move(position)

        self.hw.tower.move = MagicMock(side_effect=side_effect_move)
        wizard = SelfTestWizard(self.package)

        def on_state_changed(state):
            if state == WizardState.PREPARE_WIZARD_PART_1:
                wizard.prepare_wizard_part_1_done()
            if state == WizardState.TEST_AUDIO:
                wizard.report_audio(True)
            if state == WizardState.TEST_DISPLAY:
                wizard.report_display(True)
            if state == WizardState.PREPARE_WIZARD_PART_2:
                wizard.prepare_wizard_part_2_done()
            if state == WizardState.PREPARE_WIZARD_PART_3:
                wizard.prepare_wizard_part_3_done()
            if state == WizardState.SHOW_RESULTS:
                wizard.show_results_done()

        wizard.state_changed.connect(on_state_changed)
        self._run_wizard(wizard, expected_state=expected_state, limit_s=100000)

        wizard_data_path = defines.configDir / wizard.get_data_filename()
        self.assertTrue(wizard_data_path.exists(), "Wizard data file exists")
        print(f"Wizard data:\n{wizard_data_path.read_text()}")
        with wizard_data_path.open("rt") as file:
            data = serializer.load(file)
            return data

    @patch("slafw.defines.fanWizardStabilizeTime", 0)
    @patch("slafw.defines.fanStartStopTime", 0)
    def test_self_test_success(self):
        data = self._run_self_test()
        self.assertEqual("CZPX0819X009XC00151", data["a64SerialNo"])
        self.assertIn("osVersion", data)
        self.assertEqual("CZPX0619X678XC12345", data["mcSerialNo"])
        self.assertEqual("1.0.0", data["mcFwVersion"])
        self.assertEqual("6c", data["mcBoardRev"])

        self.assertEqual(150000000, data["tower_height_nm"])
        self.assertEqual(4928, data["tiltHeight"])
        self.assertIn("uvPwm", data)

        self.assertEqual(42, data["mock selftest result"])
        self.assertListEqual(
            [self.hw.config.fan1Rpm, self.hw.config.fan2Rpm, self.hw.config.fan3Rpm],
            data["wizardFanRpm"],
        )
        self.assertEqual(46.7, data["wizardTempUvInit"])
        self.assertEqual(46.7, data["wizardTempUvWarm"])
        self.assertEqual(26.1, data["wizardTempAmbient"])
        self.assertEqual(40, data["wizardTempA64"])
        self.assertEqual(12.8, data["wizardResinTriggeredMM"])
        self.assertEqual(0, data["towerSensitivity"])
        self._assert_final_state("showWizard", expected_value=False)

    def test_self_test_fail(self):
        self.hw.config.uvWarmUpTime = 1
        wizard = SelfTestWizard(self.package)

        def on_state_changed(state):
            if state == WizardState.PREPARE_WIZARD_PART_1:
                wizard.cancel()

        wizard.state_changed.connect(on_state_changed)
        self._run_wizard(wizard, limit_s=1, expected_state=WizardState.CANCELED)
        self._assert_final_state("showWizard", expected_value=None)

    def _assert_final_state(self, item: str, expected_value: Optional[bool]):
        conf = HwConfig(self.hw_config_file)
        conf.read_file()
        if expected_value is None:
            self.assertTrue(conf.get_values().get(item).is_default(conf))
        else:
            self.assertEqual(expected_value, getattr(conf, item))

    @patch("slafw.defines.fanWizardStabilizeTime", 0)
    @patch("slafw.defines.fanStartStopTime", 0)
    def test_self_test_tower_sensitivity_change(self):
        # side_effect = [
        #   TowerHomeFailed() - causes tower to update sensitivity to 0
        #   TowerHomeFailed() - causes tower to update sensitivity to 1
        #   True - the rest of the homing are successful
        # ]

        self.hw.tower.sync_ensure_async = MagicMock(side_effect=[
            TowerHomeFailed(),
            AsyncMock().__call__(),
            AsyncMock().__call__(),
            AsyncMock().__call__()])
        data = self._run_self_test()
        self.assertEqual(0, data["towerSensitivity"])

        self.hw.tower.sync_ensure_async = MagicMock(side_effect=[
            TowerHomeFailed(),
            TowerHomeFailed(),
            AsyncMock().__call__(),
            AsyncMock().__call__(),
            AsyncMock().__call__()])
        data = self._run_self_test()
        self.assertEqual(1, data["towerSensitivity"])

        self.hw.tower.sync_ensure_async = MagicMock(side_effect=[
            TowerEndstopNotReached(),
            TowerEndstopNotReached(),
            AsyncMock().__call__(),
            AsyncMock().__call__(),
            AsyncMock().__call__()])
        data = self._run_self_test()
        self.assertEqual(1, data["towerSensitivity"])

        self.hw.tower.sync_ensure_async = MagicMock(side_effect=[
            TowerHomeFailed(),
            TowerHomeFailed(),
            TowerHomeFailed(),
            AsyncMock().__call__(),
            AsyncMock().__call__(),
            AsyncMock().__call__()])
        data = self._run_self_test()
        self.assertEqual(2, data["towerSensitivity"])

        self.hw.tower.sync_ensure_async = Mock(side_effect=TowerHomeFailed())
        self._run_self_test(expected_state=WizardState.FAILED)

        self.hw.tower.sync_ensure_async = Mock(
            side_effect=TowerEndstopNotReached())
        self._run_self_test(expected_state=WizardState.FAILED)

    def test_unboxing_complete(self):
        wizard = CompleteUnboxingWizard(self.package)

        def on_state_changed(state):
            if state == WizardState.REMOVE_SAFETY_STICKER:
                wizard.safety_sticker_removed()
            if state == WizardState.REMOVE_SIDE_FOAM:
                wizard.side_foam_removed()
            if state == WizardState.REMOVE_TANK_FOAM:
                wizard.tank_foam_removed()
            if state == WizardState.REMOVE_DISPLAY_FOIL:
                wizard.display_foil_removed()
            if state == WizardState.SHOW_RESULTS:
                wizard.show_results_done()

        wizard.state_changed.connect(on_state_changed)
        self._run_wizard(wizard)

    def test_unboxing_kit(self):
        wizard = KitUnboxingWizard(self.package)

        def on_state_changed(state):
            if state == WizardState.REMOVE_DISPLAY_FOIL:
                wizard.display_foil_removed()
            if state == WizardState.SHOW_RESULTS:
                wizard.show_results_done()

        wizard.state_changed.connect(on_state_changed)
        self._run_wizard(wizard)

    def test_packing_complete(self):
        self.hw.config.showWizard = False
        self.hw.config.calibrated = True
        self.hw.config.tower_height_nm = Nm(0)
        self.package.runtime_config.factory_mode = True
        wizard = PackingWizard(self.package)

        def on_state_changed(state):
            if state == WizardState.INSERT_FOAM:
                wizard.foam_inserted()

        wizard.state_changed.connect(on_state_changed)
        self._run_wizard(wizard)
        self._check_factory_reset(self.hw, unboxing=True, factory_mode=True)

    def test_packing_kit(self):
        self.hw.config.showWizard = False
        self.package.runtime_config.factory_mode = True
        self.hw.mock_is_kit = True
        self._run_wizard(PackingWizard(self.package))
        self._check_factory_reset(self.hw, unboxing=True, factory_mode=True)

    def test_factory_reset_complete(self):
        self.package.runtime_config.factory_mode = False
        self._run_wizard(FactoryResetWizard(self.package, True))
        self._check_factory_reset(self.hw, unboxing=False, factory_mode=False)

    def test_factory_reset_complete_sl1s(self):
        set_configured_printer_model(PrinterModel.SL1S)
        hw = HardwareMock(HwConfig(self.hw_config_file, is_master=True), PrinterModel.SL1S)
        runtime_config = RuntimeConfig()
        runtime_config.factory_mode = False
        package = WizardDataPackage(
                hw=hw,
                config_writers=make_config_writers(hw.config),
                runtime_config=runtime_config
        )
        self._run_wizard(FactoryResetWizard(package, True))
        self._check_factory_reset(hw, unboxing=False, factory_mode=False)

    def test_factory_reset_complete_m1(self):
        set_configured_printer_model(PrinterModel.M1)
        hw = HardwareMock(HwConfig(self.hw_config_file, is_master=True), PrinterModel.M1)
        runtime_config = RuntimeConfig()
        runtime_config.factory_mode = False
        package = WizardDataPackage(
                hw=hw,
                config_writers=make_config_writers(hw.config),
                runtime_config=runtime_config
        )
        self._run_wizard(FactoryResetWizard(package, True))
        self._check_factory_reset(hw, unboxing=False, factory_mode=False)

    def test_factory_reset_kit(self):
        self.package.runtime_config.factory_mode = False
        self.hw.mock_is_kit = True
        self._run_wizard(FactoryResetWizard(self.package, True))
        self._check_factory_reset(self.hw, unboxing=False, factory_mode=False)

    def _check_factory_reset(self, hw, unboxing: bool, factory_mode: bool):
        # Assert factory reset was performed
        self.assertEqual(unboxing, hw.config.showUnboxing)
        self.assertFalse(defines.http_digest_password_file.exists(), "Digest file deleted")

        self.assertFalse(defines.slicerProfilesFile.exists(), "Slicer profiles removed")

        self.assertEqual(
            factory_mode,
            bool(list(defines.internalProjectPath.glob("*"))),
            "Internal projects removed",
        )

        hw_config = HwConfig(self.hw_config_file)
        hw_config.read_file()
        self.assertTrue(hw_config.showUnboxing == unboxing, "config reset check")
        self.assertEqual(not factory_mode, defines.factory_enable.exists(), "factory is disabled check")
        self.assertFalse(defines.serial_service_enabled.exists(), "serial is disabled check")
        self.assertFalse(defines.ssh_service_enabled.exists(), "ssh is disabled check")
        self.assertEqual(
            pydbus.SystemBus().get("org.freedesktop.NetworkManager").ListConnections(),
            [],
        )  # all connections deleted

        self.assertEqual(False, defines.prusa_printer_settings.exists())
        self.assertNotEqual(self.hostname.Hostname, "")
        self.assertNotEqual(self.hostname.StaticHostname, "")
        self.assertEqual(self.hostname.StaticHostname, self.hostname.Hostname)
        self.assertEqual(self.hostname.Hostname, defines.default_hostname + hw.printer_model.name.lower())
        self.assertTrue(self.time_date.is_default_ntp(), "NTP reset to default")
        print(self.locale.Locale)
        self.assertTrue(self.locale.is_default(), "Locale set to default")
        self.assertFalse(self.touch_ui_config.exists(), "Touch UI config removed")
        self.assertFalse(self.backlight_state.exists(), "Backlight state cleared")

        # Local time should be actually replaced by default,
        # but the copyfile is mocked. This only checks successful delete.
        self.assertFalse(defines.local_time_path.exists(), "Timezone reset to default")

    def test_calibration_success(self):
        original_move = self.hw.tower.move

        def side_effect_move(position):
            if position == self.hw.tower.min_nm:
                original_move(self.hw.tower.min_nm + Nm(1))
            else:
                original_move(position)

        self.hw.tower.move = MagicMock(side_effect=side_effect_move)
        wizard = CalibrationWizard(self.package)

        def on_state_changed(state):
            if state == WizardState.PREPARE_CALIBRATION_INSERT_PLATFORM_TANK:
                wizard.prepare_calibration_platform_tank_done()
            if state == WizardState.PREPARE_CALIBRATION_TILT_ALIGN:
                wizard.prepare_calibration_tilt_align_done()
            if state == WizardState.LEVEL_TILT:
                self.hw.tilt.position = Ustep(4992)
                wizard.tilt_aligned()
            if state == WizardState.PREPARE_CALIBRATION_PLATFORM_ALIGN:
                wizard.prepare_calibration_platform_align_done()
            if state == WizardState.PREPARE_CALIBRATION_FINISH:
                wizard.prepare_calibration_finish_done()
            if state == WizardState.SHOW_RESULTS:
                wizard.show_results_done()

        wizard.state_changed.connect(on_state_changed)
        self._run_wizard(wizard)
        self._assert_final_state(item="calibrated", expected_value=True)

    def test_calibration_fail(self):
        wizard = CalibrationWizard(self.package)

        def on_state_changed(state):
            if state == WizardState.PREPARE_CALIBRATION_INSERT_PLATFORM_TANK:
                wizard.cancel()

        wizard.state_changed.connect(on_state_changed)
        self._run_wizard(wizard, limit_s=1, expected_state=WizardState.CANCELED)
        self._assert_final_state(item="calibrated", expected_value=False)

    def test_new_expo_panel(self):
        copyfile(self.SAMPLES_DIR / defines.expoPanelLogFileName, defines.expoPanelLogPath)

        uv_usage = self.hw.uv_led.usage_s
        display_usage = self.hw.exposure_screen.usage_s
        wizard = NewExpoPanelWizard(self.package)

        def on_state_changed(state):
            if state == WizardState.PREPARE_NEW_EXPO_PANEL:
                wizard.new_expo_panel_done()

        wizard.state_changed.connect(on_state_changed)
        self._run_wizard(wizard, limit_s=15, expected_state=WizardState.DONE)

        self.assertEqual(self.hw.uv_led.usage_s, uv_usage)
        self.assertEqual(self.hw.exposure_screen.usage_s, 0)
        with open(defines.expoPanelLogPath, "r", encoding="utf-8") as f:
            log = json.load(f)
        last_key = list(log)[-1]
        self.assertEqual(log[last_key]["panel_sn"], self.hw.exposure_screen.serial_number)
        next_to_last_key = list(log)[-2]
        self.assertEqual(log[next_to_last_key]["counter_s"], display_usage)
        self._assert_final_state(item="showWizard", expected_value=True)
        self._assert_final_state(item="calibrated", expected_value=False)


class TestUVCalibration(TestWizardsBase):
    def setUp(self) -> None:
        super().setUp()
        defines.counterLog = self.TEMP_DIR / "counter.log"
        set_configured_printer_model(PrinterModel.SL1)
        self.uv_meter = UVMeterMock(self.hw)

    def tearDown(self) -> None:
        del self.hw
        del self.uv_meter
        super().tearDown()

    def test_uv_calibration_no_boost(self):
        with patch("slafw.wizard.wizards.uv_calibration.UvLedMeterMulti", self.uv_meter):
            wizard = UVCalibrationWizard(self.package, False, False)
            self._run_uv_calibration(wizard)

        # Check wizard data
        self.assertFalse(wizard.data["boost"])
        self.assertEqual("CZPX0819X009XC00151", wizard.data["a64SerialNo"])
        self.assertEqual("CZPX0619X678XC12345", wizard.data["mcSerialNo"])
        self.assertEqual("6c", wizard.data["mcBoardRev"])
        self.assertEqual(6912, wizard.data["uvLedCounter_s"])
        self.assertEqual(3600, wizard.data["displayCounter_s"])
        self.assertEqual(0, wizard.data["uvSensorType"])
        self.assertListEqual([140.7 for _ in range(15)], wizard.data["uvSensorData"])
        self.assertEqual(140.7, wizard.data["uvMean"])
        self.assertEqual(0.0, wizard.data["uvStdDev"])
        self.assertEqual(140.7, wizard.data["uvMinValue"])
        self.assertEqual(140.7, wizard.data["uvMaxValue"])
        self.assertEqual(201, wizard.data["uvFoundPwm"])
        self._assert_final_uv_pwm(self.hw.uv_led.parameters.min_pwm)

    def test_uv_calibration_boost(self):
        with patch("slafw.wizard.wizards.uv_calibration.UvLedMeterMulti", self.uv_meter):
            wizard = UVCalibrationWizard(self.package, False, False)
            self.uv_meter.multiplier = 0.79
            self._run_uv_calibration(wizard)
            self.assertTrue(wizard.data["boost"])  # Boosted as led+display too weak
            self.assertFalse(defines.counterLog.exists())  # Counter log not written as nothing was reset
        self._assert_final_uv_pwm(self.hw.uv_led.parameters.min_pwm)

    def test_uv_calibration_boost_difference(self):
        with patch("slafw.wizard.wizards.uv_calibration.UvLedMeterMulti", self.uv_meter):
            self.hw.config.data_factory_values["uvPwm"] = 100
            wizard = UVCalibrationWizard(self.package, False, False)
            self.uv_meter.multiplier = 0.85
            self._run_uv_calibration(wizard)
            self.assertTrue(wizard.data["boost"])  # Boosted as PWM differs too much from previous setup
        self._assert_final_uv_pwm(self.hw.uv_led.parameters.min_pwm)

    def test_uv_calibration_no_boost_replace_display(self):
        with patch("slafw.wizard.wizards.uv_calibration.UvLedMeterMulti", self.uv_meter):
            self.hw.config.data_factory_values["uvPwm"] = 100
            wizard = UVCalibrationWizard(self.package, True, False)
            self.uv_meter.multiplier = 0.85
            self._run_uv_calibration(wizard)
            self.assertFalse(wizard.data["boost"])  # Not boosted despite difference from previous setup, setup changed

            self.assertEqual(0, self.hw.exposure_screen.usage_s)  # Display replaced
            self.assertEqual(6912, self.hw.uv_led.usage_s)  # UV LED stays
            self.assertTrue(defines.counterLog.exists())  # Counter log written as display was replaced
            with defines.counterLog.open("r") as f:
                log = toml.load(f)
                for data in log.values():
                    # Log record contains original counter values
                    self.assertEqual(6912, data["uvLed_seconds"])
                    self.assertEqual(3600, data["display_seconds"])
        self._assert_final_uv_pwm(self.hw.uv_led.parameters.min_pwm)

    def test_uv_calibration_boost_replace_led(self):
        with patch("slafw.wizard.wizards.uv_calibration.UvLedMeterMulti", self.uv_meter):
            wizard = UVCalibrationWizard(self.package, False, True)
            self.uv_meter.multiplier = 0.75
            self._run_uv_calibration(wizard)
            self.assertTrue(wizard.data["boost"])  # Too weak needs boost even when changed

            self.assertEqual(3600, self.hw.exposure_screen.usage_s)  # Display stays
            self.assertEqual(0, self.hw.uv_led.usage_s)  # UV LED replaced
            self.assertTrue(defines.counterLog.exists())  # Counter log written as UV LED was replaced
        self._assert_final_uv_pwm(self.hw.uv_led.parameters.min_pwm)

    def test_uv_calibration_dim(self):
        with patch("slafw.wizard.wizards.uv_calibration.UvLedMeterMulti", self.uv_meter):
            wizard = UVCalibrationWizard(self.package, False, False)
            self.uv_meter.multiplier = 0.1
            self._run_uv_calibration(wizard, expected_state=WizardState.FAILED)
            self.assertIsInstance(wizard.exception, UVTooDimm)
        self._assert_final_uv_pwm(0)

    def test_uv_calibration_bright(self):
        with patch("slafw.wizard.wizards.uv_calibration.UvLedMeterMulti", self.uv_meter):
            wizard = UVCalibrationWizard(self.package, False, False)
            self.uv_meter.multiplier = 10
            self._run_uv_calibration(wizard, expected_state=WizardState.FAILED)
            self.assertIsInstance(wizard.exception, UVTooBright)
        self._assert_final_uv_pwm(0)

    def test_uv_calibration_dev(self):
        with patch("slafw.wizard.wizards.uv_calibration.UvLedMeterMulti", self.uv_meter):
            wizard = UVCalibrationWizard(self.package, False, False)
            self.uv_meter.noise = 70
            self._run_uv_calibration(wizard, expected_state=WizardState.FAILED)
            self.assertIsInstance(wizard.exception, UVDeviationTooHigh)
        self._assert_final_uv_pwm(0)

    def _run_uv_calibration(self, wizard: UVCalibrationWizard, expected_state=WizardState.DONE):
        def on_state_changed(state):
            if state == WizardState.TEST_DISPLAY:
                wizard.report_display(True)
            if state == WizardState.UV_CALIBRATION_PREPARE:
                wizard.uv_calibration_prepared()
            if state == WizardState.UV_CALIBRATION_PLACE_UV_METER:
                wizard.uv_meter_placed()
            if state == WizardState.UV_CALIBRATION_APPLY_RESULTS:
                wizard.uv_apply_result()
            if state == WizardState.STOPPED:
                wizard.abort()
            if state == WizardState.SHOW_RESULTS:
                wizard.show_results_done()

        wizard.state_changed.connect(on_state_changed)
        self._run_wizard(wizard, limit_s=15, expected_state=expected_state)

    def _assert_final_uv_pwm(self, expected_value: int):
        conf = HwConfig(self.hw_config_file)
        conf.read_file()
        self.assertLessEqual(expected_value, conf.uvPwm)


class TankSurfaceCleanerTest(TestWizardsBase):
    # pylint: disable=too-many-instance-attributes
    def setUp(self) -> None:
        super().setUp()
        self.hw.config.calibrated = True
        self.wizard = TankSurfaceCleaner(self.package)
        self.wizard.state_changed.connect(self.on_state_changed)

        self.exposure_start_time = None
        self.exposure_end_time = None

        original_move = self.hw.tower.move

        def side_effect_move(position):
            if position == self.hw.config.tankCleaningAdaptorHeight_nm - Nm(3_000_000):
                original_move(self.hw.config.tankCleaningAdaptorHeight_nm)
            else:
                original_move(position)

        self.hw.tower.move = MagicMock(side_effect=side_effect_move)

    def tearDown(self) -> None:
        del self.hw
        super().tearDown()

    def on_state_changed(self, state):
        if state == WizardState.TANK_SURFACE_CLEANER_INIT:
            self.wizard.tank_surface_cleaner_init_done()
        if state == WizardState.TANK_SURFACE_CLEANER_INSERT_CLEANING_ADAPTOR:
            self.wizard.insert_cleaning_adaptor_done()
        if state == WizardState.TANK_SURFACE_CLEANER_REMOVE_CLEANING_ADAPTOR:
            self.wizard.remove_cleaning_adaptor_done()

    def test_tank_surface_cleaner(self):
        self._run_wizard(self.wizard, limit_s=10000)

    def test_tank_surface_cleaner_fail_safe(self):
        def on_check_states_changed():
            if WizardCheckType.EXPOSING_DEBRIS in self.wizard.check_state \
                    and self.wizard.check_state[WizardCheckType.EXPOSING_DEBRIS] == WizardCheckState.RUNNING:
                time.sleep(1)
                self.wizard.cancel()
            if WizardCheckType.EXPOSING_DEBRIS in self.wizard.check_state \
                    and self.wizard.check_state[WizardCheckType.EXPOSING_DEBRIS] == WizardCheckState.CANCELED:
                assert not self.hw.uv_led.active

        self.wizard.check_states_changed.connect(on_check_states_changed)
        self._run_wizard(self.wizard, limit_s=60, expected_state=WizardState.CANCELED)

    def test_tank_surface_cleaner_exposure_time(self):
        def on_check_states_changed():
            if WizardCheckType.EXPOSING_DEBRIS in self.wizard.check_state \
                    and self.wizard.check_state[WizardCheckType.EXPOSING_DEBRIS] == WizardCheckState.RUNNING:
                self.exposure_start_time = time.time()
            if WizardCheckType.EXPOSING_DEBRIS in self.wizard.check_state \
                    and self.wizard.check_state[WizardCheckType.EXPOSING_DEBRIS] == WizardCheckState.CANCELED:
                self.exposure_end_time = time.time()
                duration = self.exposure_end_time - self.exposure_start_time
                time_diff = abs(duration - self.hw.config.tankCleaningExposureTime)
                assert time_diff < 1

        self.wizard.check_states_changed.connect(on_check_states_changed)
        self._run_wizard(self.wizard, limit_s=60)

    def test_tank_surface_cleaner_without_calibration(self):
        self.hw.config.calibrated = False
        self.wizard = TankSurfaceCleaner(self.package)
        self.wizard.state_changed.connect(self.on_state_changed)

        self._run_wizard(self.wizard, limit_s=60, expected_state=WizardState.FAILED)

if __name__ == "__main__":
    unittest.main()
