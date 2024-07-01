# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2024 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

# pylint: disable=too-few-public-methods

import os
import unittest
from time import sleep

from pydbus import SystemBus, Variant

from slafw import defines
from slafw.api.standard0 import Standard0, Standard0State
from slafw.tests.integration.base import SlaFwIntegrationTestCaseBase


class TestIntegrationStandard0(SlaFwIntegrationTestCaseBase):
    def setUp(self):
        super().setUp()

        # Fake calibration
        self.printer.hw.config.calibrated = True
        self.printer.hw.config.showWizard = False
        self.printer.hw.config.fanCheck = False
        self.printer.hw.config.coverCheck = False
        self.printer.hw.config.resinSensor = False

        # dbus
        bus = SystemBus()
        self.standard0_dbus = bus.publish(Standard0.__INTERFACE__, Standard0(self.printer))

        # Resolve standard printer and open project
        self.standard0: Standard0 = bus.get("cz.prusa3d.sl1.standard0")
        self.standard0.cmd_select(
                str(self.SAMPLES_DIR / ("numbers" + self.printer.hw.printer_model.extension)),
                False,
                False)

    def tearDown(self):
        self.standard0_dbus.unpublish()
        super().tearDown()

    def test_read_printer_values(self):
        self.assertEqual(Standard0State.SELECTED.value, self.standard0.state)
        self.assertKeysIn(['temp_led', 'temp_amb', 'cpu_temp'], self.standard0.hw_temperatures)
        self.assertDictEqual({'uv_led': 0, 'blower': 0, 'rear': 0, 'rear_target': 1000}, self.standard0.hw_fans)
        self.assertKeysIn(['cover_closed', 'temperatures', 'fans', 'state'], self.standard0.hw_telemetry)

        # it needs Hostname and NetworkManager dbus
        # self.assertEqual(str, type(self.standard0.net_hostname))
        # self.assertEqual(dict, type(self.standard0.info))
        # self.assertEqual(type,  type(self.standard0.net_ip))

    def test_read_project_values(self):
        self.assertEqual(
                "numbers" + self.printer.hw.printer_model.extension,
                os.path.basename(self.standard0.project_path))
        self.assertDictEqual(
            {
                'exposure_time_ms': 1000,
                'calibrate_time_ms': 1000,
                'calibration_regions': 0,
                'exposure_time_first_ms': 1000
            },
            self.standard0.project_get_properties(["exposure_times"])
        )
        self.standard0.project_set_properties({ "exposure_time_ms": Variant("i", 1042) })
        self.assertDictEqual({ "exposure_time_ms": 1042 }, self.standard0.project_get_properties(["exposure_time_ms"]))

    def test_resin_refilled(self):
        self.standard0.cmd_confirm()
        self._wait_for_state(Standard0State.BUSY, 60) # exposure.HOMING_AXIS
        self._wait_for_state(Standard0State.POUR_IN_RESIN, 10) # exposure.POUR_IN_RESIN
        self.standard0.cmd_continue()
        self._wait_for_state(Standard0State.BUSY, 60) # exposure.CHECKS
        self._wait_for_state(Standard0State.PRINTING, 60)
        self.standard0.cmd_pause()
        self._wait_for_state(Standard0State.FEED_ME, 30)
        self.standard0.cmd_resin_refill()
        self.standard0.cmd_continue()
        self._wait_for_state(Standard0State.BUSY, 60)  # resin stirring
        self._wait_for_state(Standard0State.PRINTING, 30)
        self.assertEqual(self.standard0.job["remaining_material"], defines.resinMaxVolume)
        self.standard0.cmd_cancel()
        self._wait_for_state(Standard0State.STOPPED, 30)

    def test_resin_not_refilled(self):
        self.standard0.cmd_confirm()
        self._wait_for_state(Standard0State.BUSY, 60)  # exposure.HOMING_AXIS
        self._wait_for_state(Standard0State.POUR_IN_RESIN, 10)  # exposure.POUR_IN_RESIN
        self.standard0.cmd_continue()
        self._wait_for_state(Standard0State.BUSY, 60)  # exposure.CHECKS
        self._wait_for_state(Standard0State.PRINTING, 60)
        resin_volume = self.standard0.job["remaining_material"]
        self.standard0.cmd_pause()
        self._wait_for_state(Standard0State.FEED_ME, 30)
        self.standard0.cmd_continue()
        self._wait_for_state(Standard0State.BUSY, 60)  # resin stirring
        self._wait_for_state(Standard0State.PRINTING, 30)
        self.assertEqual(self.standard0.job["remaining_material"], resin_volume)
        # wait for end
        self._wait_for_state(Standard0State.FINISHED, 60)

    def _wait_for_state(self, state: Standard0State, timeout_s: int):
        printer_state = None
        for _ in range(timeout_s):
            printer_state = Standard0State(self.standard0.state)
            if printer_state == state:
                break
            print(f"Waiting for state: {state}, current state: {printer_state}")
            sleep(1)
        self.assertEqual(state, printer_state)
        print(f"Finished waiting for state: {state}")

    def assertKeysIn(self, keys:list, container:dict):
        for key in keys:
            self.assertIn(key, container)


if __name__ == "__main__":
    unittest.main()
