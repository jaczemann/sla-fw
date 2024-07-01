# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import shutil
import weakref
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory
from threading import Thread
# import cProfile
from typing import Optional, List
from unittest.mock import patch

from pydbus import SystemBus

from slafw import defines, test_runtime
from slafw.api.printer0 import Printer0
from slafw.libPrinter import Printer
from slafw.tests.base import SlafwTestCaseDBus, RefCheckTestCase
from slafw.states.printer import PrinterState


class SlaFwIntegrationTestCaseBase(SlafwTestCaseDBus, RefCheckTestCase):
    # pylint: disable = too-many-instance-attributes
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.printer: Optional[Printer] = None
        self.thread: Optional[Thread] = None

    def setUp(self):
        super().setUp()

        print(f"<<<<<===== {self.id()} =====>>>>>")
        copyfile(self.SAMPLES_DIR / "hardware.cfg", self.hardware_file)
        copyfile(self.SAMPLES_DIR / "hardware.toml", self.hardware_factory_file)
        copyfile(self.SAMPLES_DIR / "api.key", defines.http_digest_password_file)
        shutil.copy(self.SAMPLES_DIR / "self_test_data.json", Path(defines.factoryMountPoint))

        os.environ["SDL_AUDIODRIVER"] = "disk"
        os.environ["SDL_DISKAUDIOFILE"] = str(self.sdl_audio_file)

        self.printer = Printer()
        test_runtime.exposure_image = self.printer.exposure_image
        self.try_start_printer()

        self._printer0 = Printer0(self.printer)
        # pylint: disable = no-member
        self.printer0_dbus = SystemBus().publish(
            Printer0.__INTERFACE__,
            (None, weakref.proxy(self._printer0), self._printer0.dbus),
        )

    def patches(self) -> List[patch]:
        self.hardware_factory_file = self.TEMP_DIR / "hardware.toml"
        self.hardware_file = self.TEMP_DIR / "slafw.hardware.cfg"
        self.temp_dir_wizard_history = TemporaryDirectory()  # pylint: disable = consider-using-with
        self.sdl_audio_file = self.TEMP_DIR / "slafw.sdl_audio.raw"
        self.counter_log = self.TEMP_DIR / defines.counterLogFilename

        return super().patches() + [
            patch("slafw.defines.wizardHistoryPath", Path(self.temp_dir_wizard_history.name)),
            patch("slafw.defines.cpuSNFile", str(self.SAMPLES_DIR / "nvmem")),
            patch("slafw.defines.hwConfigPathFactory", self.hardware_factory_file),
            patch("slafw.defines.hwConfigPath", self.hardware_file),
            patch("slafw.defines.internalProjectPath", str(self.SAMPLES_DIR)),
            patch("slafw.defines.http_digest_password_file", self.TEMP_DIR / "api.key"),
            patch("slafw.defines.livePreviewImage", str(self.TEMP_DIR / "live.png")),
            patch("slafw.defines.displayUsageData", str(self.TEMP_DIR / "display_usage.npz")),
            patch("slafw.defines.serviceData", str(self.TEMP_DIR / "service.toml")),
            patch("slafw.defines.fan_check_override", True),
            patch("slafw.defines.loggingConfig", self.TEMP_DIR / "logger_config.json"),
            patch("slafw.defines.last_log_token", self.TEMP_DIR / "last_log_token"),
            patch("slafw.defines.counterLog", self.counter_log),
        ]

    def try_start_printer(self):
        try:
            self.printer.setup()
            self.printer.set_state(PrinterState.RUNNING)
            # cProfile.runctx('self.printer.start()', globals=globals(), locals=locals())
        except Exception as exception:
            self.tearDown()
            raise Exception("Test setup failed") from exception

    def tearDown(self):
        self.printer0_dbus.unpublish()
        # This fixes symptoms of a bug in pydbus. Drop circular dependencies.
        if self._printer0 in Printer0.PropertiesChanged.map:  # pylint: disable = no-member
            del Printer0.PropertiesChanged.map[self._printer0]  # pylint: disable = no-member
        if self._printer0 in Printer0.exception.map:  # pylint: disable = no-member
            del Printer0.exception.map[self._printer0]  # pylint: disable = no-member

        self.printer.stop()

        # Make sure we are not leaving these behind.
        # Base test tear down checks this does not happen.
        del self.printer
        del self._printer0

        files = [
            self.EEPROM_FILE,
            self.hardware_file,
            self.sdl_audio_file,
        ]

        for file in files:
            if file.exists():
                file.unlink()

        self.temp_dir_wizard_history.cleanup()
        print(f"<<<<<===== {self.id()} =====>>>>>")
        super().tearDown()  # closes logger!

    @staticmethod
    def call(fce):
        fce()
