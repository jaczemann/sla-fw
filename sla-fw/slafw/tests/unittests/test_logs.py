# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later
import asyncio
import os
import unittest
from functools import partial
from pathlib import Path
from threading import Event
from time import sleep
from unittest.mock import Mock, patch

import pydbus
from pydbus import SystemBus

from slafw import defines
from slafw.tests import mocks
from slafw.tests.base import SlafwTestCaseDBus, RefCheckTestCase
from slafw.api.logs0 import Logs0
from slafw.states.data_export import ExportState, StoreType


async def fake_log_export_process(log_file: Path):
    return await asyncio.create_subprocess_shell(f'(sleep 1; date) > "{log_file}"', stderr=asyncio.subprocess.PIPE)


class TestLogs0(SlafwTestCaseDBus, RefCheckTestCase):
    def setUp(self):
        super().setUp()

        defines.printer_summary = Path(defines.ramdiskPath) / "printer_summary"

        # Set path to test version of scripts (necessary for log export script to "work")
        scripts_path = Path(mocks.__file__).parent / "scripts"
        os.environ["PATH"] = os.environ["PATH"] + ":" + str(scripts_path.absolute())

        hw = Mock()
        self.waiter = Event()
        type(hw).cpuSerialNo = property(partial(self._get_serial, self.waiter))
        self.logs0_dbus = SystemBus().publish(Logs0.__INTERFACE__, Logs0(hw))
        self.logs0: Logs0 = pydbus.SystemBus().get("cz.prusa3d.sl1.logs0")

    def tearDown(self) -> None:
        self.logs0_dbus.unpublish()
        super().tearDown()

    def test_initial_state(self):
        self.assertEqual(ExportState.IDLE.value, self.logs0.state)
        self.assertEqual(StoreType.IDLE.value, self.logs0.type)
        self.assertEqual(0, self.logs0.export_progress)
        self.assertEqual(0, self.logs0.store_progress)

    @patch("slafw.state_actions.logs.logs.run_log_export_process", fake_log_export_process)
    def test_cancel(self):
        self.logs0.usb_save()
        for _ in range(50):
            sleep(0.1)
            if self.logs0.state != ExportState.IDLE:
                break
        self.logs0.cancel()
        self.waiter.set()
        for _ in range(100):
            sleep(0.1)
            if self.logs0.state in [ExportState.CANCELED.value, ExportState.FAILED.value, ExportState.FINISHED.value]:
                break
        self.assertEqual(ExportState.CANCELED.value, self.logs0.state)

    @patch("slafw.state_actions.logs.logs.run_log_export_process", fake_log_export_process)
    def test_usbsave(self):
        self.logs0.usb_save()
        self.waiter.set()
        for _ in range(600):
            sleep(0.1)
            if self.logs0.state in [ExportState.CANCELED.value, ExportState.FAILED.value, ExportState.FINISHED.value]:
                break
        self.assertEqual(StoreType.USB.value, self.logs0.type)
        self.assertEqual(ExportState.FINISHED.value, self.logs0.state)
        self.assertEqual(1, self.logs0.export_progress)
        self.assertEqual(1, self.logs0.store_progress)

    @staticmethod
    def _get_serial(waiter, _):
        waiter.wait()
        return "CZPX0819X009XC00151"


if __name__ == "__main__":
    unittest.main()
