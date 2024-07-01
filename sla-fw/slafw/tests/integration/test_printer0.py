# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import gc
import time
import unittest
import weakref
from pathlib import Path
from time import sleep
from typing import Type, List
from unittest.mock import patch, Mock

import pydbus

from gi.repository.GLib import GError

from slafw.api.exposure0 import Exposure0
from slafw.api.printer0 import Printer0State, Printer0
from slafw.api.wizard0 import Wizard0
from slafw.states.wizard import  WizardId
from slafw.errors.errors import UnknownPrinterModel
from slafw.exposure.exposure import Exposure
from slafw.functions.system import printer_model_regex
from slafw.hardware.printer_model import PrinterModel
from slafw.state_actions.manager import ActionManager
from slafw.tests.integration.base import SlaFwIntegrationTestCaseBase



class TestIntegrationPrinter0(SlaFwIntegrationTestCaseBase):
    def setUp(self):
        super().setUp()
        self.printer0: Printer0 = pydbus.SystemBus().get("cz.prusa3d.sl1.printer0")

    def test_initial_state(self):
        self.assertEqual(Printer0State.IDLE.value, self.printer0.state)

    def test_homing(self):
        self.printer0.tower_home()
        self.printer0.tilt_home()
        self.printer0.disable_motors()

    def test_control_moves(self):
        self.printer0.tower_move(2)
        sleep(0.1)
        self.printer0.tower_move(0)
        sleep(0.1)
        self.printer0.tower_move(1)
        sleep(0.1)
        self.printer0.tower_move(0)
        sleep(0.1)
        self.printer0.tower_move(-1)
        sleep(0.1)
        self.printer0.tower_move(0)
        sleep(0.1)
        self.printer0.tower_move(-2)
        sleep(0.1)
        self.printer0.tower_move(0)

        self.printer0.tilt_move(2)
        sleep(0.1)
        self.printer0.tilt_move(0)
        sleep(0.1)
        self.printer0.tilt_move(1)
        sleep(0.1)
        self.printer0.tilt_move(0)
        sleep(0.1)
        self.printer0.tilt_move(-1)
        sleep(0.1)
        self.printer0.tilt_move(0)
        sleep(0.1)
        self.printer0.tilt_move(-2)
        sleep(0.1)
        self.printer0.tilt_move(0)

    def test_absolute_moves(self):
        self.printer0.tower_home()
        initial = self.printer0.tower_position_nm
        offset = 12500
        self.printer0.tower_position_nm += offset
        for _ in range(1, 30):
            sleep(0.1)
            if self.printer0.tower_position_nm == initial + offset:
                break
        self.assertAlmostEqual(self.printer0.tower_position_nm, initial + offset, 12500)

        self.printer0.tilt_home()
        initial = self.printer0.tilt_position
        offset = 12500
        self.printer0.tilt_position += offset
        for _ in range(1, 30):
            sleep(0.1)
            if self.printer0.tilt_position == initial + offset:
                break
        self.assertAlmostEqual(self.printer0.tilt_position, initial + offset, 12500)

    def test_info_read(self):
        self.assertEqual(self.printer0.serial_number, "CZPX0819X009XC00151")
        self.assertGreater(len(self.printer0.system_name), 3)
        self.assertEqual(type(self.printer0.system_name), str)
        self.assertEqual(type(self.printer0.system_version), str)
        self.assertEqual(
            {
                "rpm": 0,
                "error": 0,
            },
            self.printer0.uv_led_fan
        )
        self.assertEqual(
            {
                "rpm": 0,
                "error": 0,
            },
            self.printer0.blower_fan
        )
        self.assertEqual(
            {
                "rpm": 0,
                "error": 0,
            },
            self.printer0.rear_fan
        )
        self.assertEqual(type(self.printer0.cpu_temp), float)
        if PrinterModel() == PrinterModel.SL1:
            self.assertEqual(
                self.printer0.leds,
                {
                    "led0_voltage_volt": 0.0,
                    "led1_voltage_volt": 0.0,
                    "led2_voltage_volt": 0.0,
                    "led3_voltage_volt": 24.0,
                },
            )
        else:
            self.assertEqual(self.printer0.leds, {})
        # TODO: Statistics report out of range integer
        # self.assertTrue('uv_stat0' in self.printer0.uv_statistics)
        self.assertRegex(self.printer0.controller_sw_version, ".*\\..*\\..*")
        self.assertEqual(self.printer0.controller_serial, "CZPX0619X678XC12345")
        self.assertEqual(self.printer0.controller_revision, "6c")
        self.assertEqual(self.printer0.http_digest_password, "32LF9aXN")
        self.printer0.enable_resin_sensor(True)
        self.printer0.enable_resin_sensor(False)
        self.assertEqual(self.printer0.cover_state, False)
        self.assertEqual(self.printer0.power_switch_state, False)
        self.assertTrue(self.printer0.factory_mode)
        self.assertTrue(self.printer0.admin_enabled)

        # self.printer0.print()

    def test_project_list_raw(self):
        project_list = self.printer0.list_projects_raw()
        self.assertTrue(project_list)
        for project in project_list:
            self.assertTrue(Path(project).is_file())
            self.assertRegex(Path(project).name, r".*\." + printer_model_regex())

    def test_print_start(self):
        # Fake calibration
        self.printer.hw.config.calibrated = True
        self.printer.hw.config.showWizard = False

        # Test print start
        path = self.printer0.print(
                str(self.SAMPLES_DIR / ("numbers" + self.printer.hw.printer_model.extension)),
                False)
        self.assertNotEqual(path, "/")
        self.assertEqual(Printer0State.PRINTING, Printer0State(self.printer0.state))

    def test_exposure_gc(self):
        # Fake calibration
        self.printer.hw.config.calibrated = True
        self.printer.hw.config.showWizard = False

        initial_exposure0 = self._get_num_instances(Exposure0)
        initial_exposure = self._get_num_instances(Exposure)

        # Start and cancel more than max exposures -> force exposure gc
        for _ in range(ActionManager.MAX_EXPOSURES + 1):
            path = self.printer0.print(
                    str(self.SAMPLES_DIR / ("numbers" + self.printer.hw.printer_model.extension)),
                    False)
            exposure0 = pydbus.SystemBus().get("cz.prusa3d.sl1.exposure0", path)
            exposure0.cancel()

        # Make sure we are not keeping extra exposure objects
        self.assertEqual(self._get_num_instances(Exposure0) - initial_exposure0, ActionManager.MAX_EXPOSURES)
        self.assertEqual(self._get_num_instances(Exposure) - initial_exposure, ActionManager.MAX_EXPOSURES)

    def test_temps(self):
        # SL1S, M1 have UV temp on index 2, but the simulator does not reflect the change
        if self.printer.hw.printer_model == PrinterModel.SL1:
            self.assertAlmostEqual(40, self.printer0.uv_led_temp)
            self.assertAlmostEqual(20, self.printer0.ambient_temp)
        elif self.printer.hw.printer_model in (PrinterModel.SL1S, PrinterModel.M1):
            self.assertAlmostEqual(20, self.printer0.uv_led_temp)
            self.assertAlmostEqual(20, self.printer0.ambient_temp)
        else:
            raise NotImplementedError

    @staticmethod
    def _get_num_instances(instance_type: Type) -> int:
        gc.collect()
        counter = 0
        for obj in gc.get_objects():
            try:
                if isinstance(obj, instance_type) and not isinstance(obj, weakref.ProxyTypes):
                    counter += 1
            except ReferenceError:
                # Weak reference target just disappeared, does not count
                pass
        return counter


class TestIntegrationUnknownPrinter0(SlaFwIntegrationTestCaseBase):
    def patches(self) -> List[patch]:
        return super().patches() + [
            patch("slafw.hardware.printer_model.PrinterModel.detect_model", Mock(side_effect=UnknownPrinterModel()))
        ]

    def setUp(self):
        super().setUp()
        self.printer0: Printer0 = pydbus.SystemBus().get("cz.prusa3d.sl1.printer0")

    def test_unknown_model(self):
        self.assertEqual(Printer0State.EXCEPTION, Printer0State(self.printer0.state))


class TestIntegrationPrinter0Uncalibrated(SlaFwIntegrationTestCaseBase):
    def setUp(self):
        super().setUp()
        self.printer0: Printer0 = pydbus.SystemBus().get("cz.prusa3d.sl1.printer0")
        self.printer.hw.config.calibrated = False

    def tearDown(self):
        super().tearDown()
        del self.printer0

    def test_initial_state(self):
        self.assertEqual(Printer0State.IDLE.value, self.printer0.state)
        self.assertEqual(False, self.printer.mechanically_calibrated)

    def test_uncalibrated_print(self):
        """
        Attempts a normal print on uncalibrated printer and checks the resulting state
        """
        # Fake NOT calibration
        self.printer.hw.config.calibrated = False
        path = None

        # Test print start on uncalibrated printer
        # Ignore all exceptions, check only the resulting state
        try:
            path = self.printer0.print(
                    str(self.SAMPLES_DIR / ("numbers" + self.printer.hw.printer_model.extension)),
                    False)
        except GError as e:
            print("GError: ", e)

        self.assertEqual(path, None)
        self.assertEqual(Printer0State.IDLE, Printer0State(self.printer0.state))

    def test_uncalibrated_oneclick_print(self):
        """
        Emulates a oneclick print where the user aborts the offered mandatory
        wizards that must run before the printer is ready to print.
        """
        # Fake calibration
        self.printer.hw.config.calibrated = False
        self.printer.hw.config.showWizard = False

        # Test print start
        # pylint: disable=protected-access
        self.printer._one_click_file(1, 2, 3, 4, [str(self.SAMPLES_DIR / ("numbers" + self.printer.hw.printer_model.extension))])

        # There might be a delay between inserting the media and running "make_ready_to_print"
        time.sleep(3)
        wizard0: Wizard0 = pydbus.SystemBus().get("cz.prusa3d.sl1.wizard0")

        self.assertEqual(WizardId.CALIBRATION, WizardId(wizard0.identifier))
        wizard0.cancel()

        self.assertEqual(Printer0State.IDLE, Printer0State(self.printer0.state))
        del wizard0

    def test_print_start(self):
        """ This time the print should start """
        # Fake calibration
        self.printer.hw.config.calibrated = True
        self.printer.hw.config.showWizard = False

        # Test print start
        path = self.printer0.print(str(self.SAMPLES_DIR / ("numbers" + self.printer.hw.printer_model.extension)), False)
        self.assertNotEqual(path, "/")
        self.assertEqual(Printer0State.PRINTING, Printer0State(self.printer0.state))


if __name__ == "__main__":
    unittest.main()
