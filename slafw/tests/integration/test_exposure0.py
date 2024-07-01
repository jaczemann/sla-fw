# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import unittest
from pathlib import Path
from time import sleep
from unittest.mock import patch

import pydbus
from prusaerrors.sl1.codes import Sl1Codes

from slafw.api.exposure0 import Exposure0State, Exposure0
from slafw.errors.errors import PrinterException
from slafw.errors.warnings import AmbientTooHot
from slafw.tests.integration.base import SlaFwIntegrationTestCaseBase


class TestIntegrationExposure0(SlaFwIntegrationTestCaseBase):
    def setUp(self):
        super().setUp()

        self.printer.hw.config.showWizard = False
        self.printer.hw.config.uvPwm = self.printer.hw.uv_led.parameters.min_pwm + 1

        #self.mechanically_calibrated and self.uv_calibrated and self.self_tested
        self.printer.hw.config.calibrated = True
        self.printer.hw.config.fanCheck = False
        self.printer.hw.config.coverCheck = False
        self.printer.hw.config.resinSensor = False
        print("MODIFIED CONFIG: ", self.printer.hw.config)
        # Resolve printer and start the print
        self.bus = pydbus.SystemBus()
        self.printer0 = self.bus.get("cz.prusa3d.sl1.printer0")
        expo_path = self.printer0.print(
                str(self.SAMPLES_DIR / ("numbers" + self.printer.hw.printer_model.extension)),
                False)
        self.exposure0: Exposure0 = self.bus.get("cz.prusa3d.sl1.exposure0", expo_path)

    def test_init(self):
        self.assertEqual(Exposure0State.CONFIRM, Exposure0State(self.exposure0.state))
        self.assertEqual("numbers" + self.printer.hw.printer_model.extension, Path(self.exposure0.project_file).name)
        self.assertEqual("numbers", self.exposure0.project_name)
        self.assertEqual(0, self.exposure0.current_layer)
        self.assertEqual(0, self.exposure0.calibration_regions)
        self.assertAlmostEqual(87.792032, self.exposure0.total_resin_required_ml, delta=0.1)
        self.assertAlmostEqual(50, self.exposure0.total_resin_required_percent, 1)

    def test_print(self):
        self.exposure0.confirm_start()
        self._wait_for_state(Exposure0State.POUR_IN_RESIN, 60)
        self.exposure0.confirm_resin_in()
        self._wait_for_state(Exposure0State.CHECKS, 5)
        self._wait_for_state(Exposure0State.PRINTING, 60)
        self.assertEqual(self.exposure0.failure_reason, PrinterException.as_dict(None))
        self._wait_for_state(Exposure0State.GOING_UP, 30)
        self._wait_for_state(Exposure0State.FINISHED, 35)
        self.assertEqual(100, self.exposure0.progress)

        # Check zipfile is closed after print
        self.assertFalse(self.printer.action_manager.exposure.project.is_open)

    def test_print_cancel(self):
        self.exposure0.confirm_start()
        self._wait_for_state(Exposure0State.POUR_IN_RESIN, 60)
        self.exposure0.cancel()
        self._wait_for_state(Exposure0State.CANCELED, 60)

    def test_print_warning(self):
        with patch("slafw.test_runtime.injected_preprint_warning", AmbientTooHot(ambient_temperature=42.0)):
            self.exposure0.confirm_start()
            self._wait_for_state(Exposure0State.POUR_IN_RESIN, 60)
            self.exposure0.confirm_resin_in()
            self._wait_for_state(Exposure0State.CHECK_WARNING, 30)

            self.assertTrue(self.exposure0.exposure_warning)
            warning = self.exposure0.exposure_warning
            self.assertEqual(warning["code"], Sl1Codes.AMBIENT_TOO_HOT_WARNING.code)
            self.assertAlmostEqual(warning["ambient_temperature"], 42.0)
            self.exposure0.reject_print_warning()
            self._wait_for_state(Exposure0State.CANCELED, 30)

            exception = self.exposure0.failure_reason
            self.assertIsNotNone(exception)
            self.assertEqual(exception["code"], Sl1Codes.WARNING_ESCALATION.code)

    def _test_home_axis(self):
        self.exposure0.confirm_start()
        self._wait_for_state(Exposure0State.HOMING_AXIS, 60)
        self._wait_for_state(Exposure0State.POUR_IN_RESIN, 60)
        self.exposure0.cancel()

    def test_home_axis_without(self):
        self._test_home_axis()

    def test_home_axis_with_tilt(self):
        self.printer.hw.tilt.sync_ensure()
        self._test_home_axis()

    def test_home_axis_with_tower(self):
        self.printer.hw.tower.sync_ensure()
        self._test_home_axis()

    def test_home_axis_with_both(self):
        self.printer.hw.tilt.sync_ensure()
        self.printer.hw.tower.sync_ensure()
        self.exposure0.confirm_start()
        for _ in range(600):
            self.assertNotEqual(Exposure0State.HOMING_AXIS, Exposure0State(self.exposure0.state))
            if self.exposure0.state == Exposure0State.POUR_IN_RESIN.value:
                break
            sleep(0.1)
        self.exposure0.cancel()

    def _wait_for_state(self, state: Exposure0State, timeout_s: int):
        for _ in range(timeout_s):
            if self.exposure0.state == state.value:
                break
            sleep(0.5)
        self.assertEqual(state, Exposure0State(self.exposure0.state))


if __name__ == '__main__':
    unittest.main()
