# This file is part of the SLA firmware
# Copyright (C) 2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import json
from datetime import datetime, timedelta
from shutil import copyfile
from typing import Optional
from unittest.mock import Mock, patch, PropertyMock

from slafw.tests.base import SlafwTestCaseDBus, RefCheckTestCase
from slafw import defines
from slafw.errors.errors import OldExpoPanel
from slafw.functions.system import set_configured_printer_model
from slafw.hardware.printer_model import PrinterModel
from slafw.states.printer import PrinterState
from slafw.libPrinter import Printer


@patch("slafw.hardware.printer_model.PrinterModel.detect_model", Mock(return_value=PrinterModel.SL1S))
class TestStartupSL1S(SlafwTestCaseDBus, RefCheckTestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.printer: Optional[Printer] = None  # This is here to provide type hint on self.printer

    def setUp(self) -> None:
        super().setUp()
        set_configured_printer_model(PrinterModel.SL1S)  # Set SL1S as the current model

        self.printer = Printer()

    def tearDown(self) -> None:
        self.printer.stop()
        del self.printer
        super().tearDown()

    def test_expo_panel_log_first_record(self):
        self._run_printer()
        self.assertEqual(self.printer.state, PrinterState.INIT)  # no wizard is running, no error is raised
        with open(defines.expoPanelLogPath, "r", encoding="utf-8") as f:
            log = json.load(f)
        self.assertEqual(1, len(log))  # log holds only one record
        last_key = list(log)[-1]
        self.assertTrue(
            abs(datetime.strptime(last_key, "%Y-%m-%d %H:%M:%S") - datetime.now().replace(microsecond=0))
            < timedelta(seconds=5)
        )
        self.assertEqual(self.printer.hw.exposure_screen.serial_number, log[last_key]["panel_sn"])
        self.assertRaises(KeyError, lambda: log[last_key]["counter_s"])

    def test_expo_panel_log_new_record(self):
        copyfile(self.SAMPLES_DIR / defines.expoPanelLogFileName, defines.expoPanelLogPath)

        self._run_printer()
        with open(defines.expoPanelLogPath, "r", encoding="utf-8") as f:
            log = json.load(f)
        self.assertEqual(3, len(log))  # log holds records from sample file

        last_key = list(log)[-1]  # last record has to be newly added
        self.assertNotEqual(
            self.printer.hw.exposure_screen.serial_number, log[last_key]["panel_sn"]
        )  # wizard is not done, so new panel is not recorded

    def test_expo_panel_log_old_panel(self):
        observer = Mock(__name__="MockObserver")
        self.printer.exception_occurred.connect(observer)
        copyfile(self.SAMPLES_DIR / defines.expoPanelLogFileName, defines.expoPanelLogPath)
        with patch(
            "slafw.hardware.sl1.hardware.SL1SExposureScreen.serial_number",
            PropertyMock(return_value="CZPX2921X021X000262"),
        ):
            self._run_printer()
        with open(defines.expoPanelLogPath, "r", encoding="utf-8") as f:
            log = json.load(f)
        next_to_last_key = list(log)[-2]  # get counter_s from sample file
        observer.assert_called_with(OldExpoPanel(counter_h=round(log[next_to_last_key]["counter_s"] / 3600)))

    def _run_printer(self):
        self.printer.setup()

        # Default setup
        self.printer.hw.config.factory_reset()  # Ensure this tests does not depend on previous config
        self.printer.hw.config.showUnboxing = False
        self.printer.hw.config.showWizard = False
        self.printer.hw.config.calibrated = True
        self.printer.hw.config.uvPwm = 208


@patch("slafw.hardware.printer_model.PrinterModel.detect_model", Mock(return_value=PrinterModel.SL1))
class TestStartupSL1(SlafwTestCaseDBus):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.printer: Optional[Printer] = None  # This is here to provide type hint on self.printer

    def setUp(self) -> None:
        super().setUp()
        set_configured_printer_model(PrinterModel.SL1)  # Set SL1S as the current model
        self.printer = Printer()

    def tearDown(self) -> None:
        self.printer.stop()
        del self.printer
        super().tearDown()

    def test_expo_panel_log_sl1(self):
        self._run_printer()
        self.printer.hw.exposure_screen.start = Mock(return_value=PrinterModel.SL1)
        set_configured_printer_model(PrinterModel.SL1)  # Set SL1 as the current model

        self.assertEqual(self.printer.state, PrinterState.INIT)  # no wizard is running, no error is raised
        self.assertFalse(defines.expoPanelLogPath.exists())

    def _run_printer(self):
        self.printer.setup()

        # Default setup
        self.printer.hw.config.factory_reset()  # Ensure this tests does not depend on previous config
        self.printer.hw.exposure_screen.start = Mock(return_value=PrinterModel.SL1)
        self.printer.hw.config.showUnboxing = False
        self.printer.hw.config.showWizard = False
        self.printer.hw.config.calibrated = True
        self.printer.hw.config.uvPwm = 208
