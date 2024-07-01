#!/usr/bin/env python

# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2021-2024 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

"""
This module is used to run a virtual printer. Virtual printer encompasses some of the real printer and parts of the
integration test mocks. All in all this launches the printer (similar to the one launched by main.py) that can run on
a desktop computer without motion controller connected. This mode is intended for GUI testing.
"""

import asyncio
import concurrent
import logging
import os
import signal
import tempfile
import threading
import warnings
from pathlib import Path
from shutil import copyfile
from typing import List
from unittest.mock import patch, Mock, AsyncMock

import pydbus
from gi.repository import GLib

import slafw.hardware.sl1.printer_model
import slafw.tests.mocks.mc_port
from slafw import defines, test_runtime
from slafw import libPrinter
from slafw.admin.manager import AdminManager
from slafw.api.admin0 import Admin0
from slafw.api.printer0 import Printer0
from slafw.api.standard0 import Standard0
from slafw.functions.system import set_configured_printer_model
from slafw.hardware.printer_model import PrinterModel
from slafw.tests import samples
from slafw.tests.mocks.dbus.rauc import Rauc
from slafw.tests.mocks.sl1s_uvled_booster import BoosterMock
from slafw.tests.mocks.wayland import WaylandMock
from slafw.hardware.sl1.tilt_profiles import TILT_CFG_LOCAL
from slafw.hardware.sl1.tower_profiles import TOWER_CFG_LOCAL
from slafw.exposure.persistence import LAST_PROJECT_DATA
from slafw.states.printer import PrinterState

# gitlab CI job creates model folder in different location due to restricted permissions in Docker container
# common path is /builds/project-0/model
from slafw.wizard.wizards.self_test import SelfTestWizard

if "CI" in os.environ:
    defines.printer_model_run = Path(os.environ["CI_PROJECT_DIR"] + "/model")
printer_model = PrinterModel()

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s", level=logging.DEBUG)

# Display warnings only once
warnings.simplefilter("once")

SAMPLES_DIR = Path(samples.__file__).parent
SLAFW_DIR = Path(slafw.__file__).parent


class Virtual:
    # pylint: disable = too-many-instance-attributes
    def __init__(self):
        self.printer = None
        self.rauc_mocks = None
        self.glib_loop = None
        self.printer0 = None
        self.standard0 = None
        self.admin_manager = None
        self.admin0_dbus = None

        self.temp_dir_obj = tempfile.TemporaryDirectory()  # pylint: disable = consider-using-with
        self.temp = Path(self.temp_dir_obj.name)

    def __call__(self):
        hardware_file = self.temp / "slafw.hardware.cfg"
        hardware_file_factory = self.temp / "slafw.hardware.cfg.factory"
        prev_prints = self.temp / "previous_prints"
        http_digest_password_file = self.temp / "api.key"

        patches: List[patch] = [
            patch("slafw.motion_controller.base_controller.serial", slafw.tests.mocks.mc_port),
            patch("slafw.libUvLedMeterMulti.serial", slafw.tests.mocks.mc_port),
            patch("slafw.motion_controller.sl1_controller.UInput", Mock()),
            patch("slafw.motion_controller.sl1_controller.chip", Mock()),
            patch("slafw.motion_controller.sl1_controller.find_line", Mock()),
            patch("slafw.motion_controller.sl1_controller.line_request", Mock()),
            patch("slafw.functions.files.get_save_path", self.fake_save_path),
            patch("slafw.hardware.sl1.hardware.HardwareSL1.isCoverClosed", Mock(return_value=True)),
            patch(
                "slafw.hardware.sl1.hardware.HardwareSL1.get_resin_volume_async",
                AsyncMock(return_value=100),
            ),
            patch("slafw.hardware.sl1.hardware.Booster", BoosterMock),
            patch("slafw.hardware.sl1.tilt.TILT_CFG_LOCAL", self.temp / TILT_CFG_LOCAL.name),
            patch("slafw.hardware.sl1.tower.TOWER_CFG_LOCAL", self.temp / TOWER_CFG_LOCAL.name),
            patch("slafw.exposure.persistence.LAST_PROJECT_DATA", self.temp / LAST_PROJECT_DATA.name),
            patch("slafw.hardware.a64.temp_sensor.A64CPUTempSensor.CPU_TEMP_PATH", SAMPLES_DIR / "cputemp"),
            patch("slafw.defines.hwConfigPath", hardware_file),
            patch("slafw.defines.hwConfigPathFactory", hardware_file_factory),
            patch("slafw.test_runtime.testing", True),
            patch("slafw.defines.cpuSNFile", str(SAMPLES_DIR / "nvmem")),
            patch("slafw.defines.internalProjectPath", str(SAMPLES_DIR)),
            patch("slafw.defines.ramdiskPath", str(self.temp)),
            patch("slafw.defines.livePreviewImage", str(self.temp / "live.png")),
            patch("slafw.defines.displayUsageData", str(self.temp / "display_usage.npz")),
            patch("slafw.defines.serviceData", str(self.temp / "service.toml")),
            patch("slafw.defines.statsData", self.temp / "stats.toml"),
            patch("slafw.defines.fan_check_override", True),
            patch("slafw.defines.mediaRootPath", str(SAMPLES_DIR)),
            patch("slafw.defines.previousPrints", prev_prints),
            patch("slafw.defines.slicerProfilesFile", self.temp / defines.profilesFile),
            patch("slafw.defines.loggingConfig", self.temp / "logging_config.json"),
            patch("slafw.defines.last_job", self.temp / "last_job"),
            patch("slafw.defines.last_log_token", self.temp / "last_log_token"),
            patch("slafw.defines.printer_summary", self.temp / "printer_summary"),
            patch("slafw.defines.slicerProfilesFile", self.temp / "slicer_profiles.toml"),
            patch("slafw.defines.emmc_serial_path", SAMPLES_DIR / "cid"),
            patch("slafw.defines.factoryMountPoint", self.temp),
            patch("slafw.defines.wizardHistoryPath", self.temp / "wizard_history" / "user_data"),
            patch("slafw.defines.wizardHistoryPathFactory", self.temp / "wizard_history" / "factory_data"),
            patch("slafw.defines.counterLog", self.temp / defines.counterLogFilename),
            patch("slafw.defines.printer_model", self.temp / "model"),
            patch("slafw.defines.firstboot", self.temp / "firstboot"),
            patch("slafw.defines.factory_enable", self.temp / "factory_mode_enabled"),
            patch("slafw.defines.exposure_panel_of_node", SAMPLES_DIR / "of_node" / printer_model.name.lower()),
            patch("slafw.defines.expoPanelLogPath", self.temp / defines.expoPanelLogFileName),
            patch("slafw.defines.http_digest_password_file", http_digest_password_file),
            patch("slafw.wizard.checks.factory_reset.ResetTimezone.reset_task_run", Mock()),
            patch("slafw.wizard.checks.factory_reset.ResetTouchUI.reset_task_run", Mock()),
            patch("slafw.wizard.checks.factory_reset.ResetUpdateChannel.reset_task_run", Mock()),
            patch("slafw.wizard.checks.factory_reset.ResetNetwork.reset_task_run", Mock()),
            patch("slafw.functions.system.os", Mock()),
            patch("slafw.api.standard0.Standard0._info_eth_mac", "00:00:00:00:00:00"),
            patch("slafw.api.standard0.Standard0._info_wlan_mac", "00:00:00:00:00:00"),
            patch("slafw.api.standard0.Standard0._info_uuid", "00000"),
            patch("distro.os_release_attr", Mock(return_value="1.8.0 blah")),
        ]

        if not os.environ.get("WAYLAND_DISPLAY") or printer_model != PrinterModel.VIRTUAL:
            patches.append(patch("slafw.hardware.exposure_screen.Wayland", WaylandMock))

        copyfile(SAMPLES_DIR / "hardware-virtual.cfg", hardware_file)
        copyfile(SAMPLES_DIR / "hardware.toml", hardware_file_factory)
        copyfile(SAMPLES_DIR / "self_test_data.json", self.temp / SelfTestWizard.get_data_filename())
        copyfile(SAMPLES_DIR / "api.key", http_digest_password_file)

        for p in patches:
            p.start()

        set_configured_printer_model(printer_model)
        copyfile(SAMPLES_DIR / defines.expoPanelLogFileName, defines.expoPanelLogPath)
        slafw.defines.wizardHistoryPathFactory.mkdir(exist_ok=True, parents=True)
        defines.wizardHistoryPath.mkdir(exist_ok=True, parents=True)
        defines.factory_enable.touch()  # Enable factory mode
        prev_prints.mkdir(exist_ok=True, parents=True)

        print("Resolving system bus")
        bus = pydbus.SystemBus()
        print("Publishing Rauc mock")
        self.rauc_mocks = bus.publish(Rauc.__OBJECT__, ("/", Rauc()))

        print("Initializing printer")
        self.printer = libPrinter.Printer()

        test_runtime.exposure_image = self.printer.exposure_image

        print("Publishing printer on D-Bus")
        self.printer0 = bus.publish(Printer0.__INTERFACE__, Printer0(self.printer))
        self.standard0 = bus.publish(Standard0.__INTERFACE__, Standard0(self.printer))
        self.admin_manager = AdminManager()
        self.admin0_dbus = bus.publish(Admin0.__INTERFACE__, Admin0(self.admin_manager, self.printer))
        print("Running printer")
        threading.Thread(target=self.printer_setup_body).start()  # Does not block, but requires Rauc on DBus
        self.printer.set_state(PrinterState.RUNNING)
        self.glib_loop = GLib.MainLoop().run()

        def tear_down(signum, _):
            if signum not in [signal.SIGTERM, signal.SIGINT]:
                return

            print("Running virtual printer tear down")
            asyncio.run(self.async_tear_down())
            print("Virtual printer teardown finished")

        signal.signal(signal.SIGINT, tear_down)
        signal.signal(signal.SIGTERM, tear_down)

        print("Running glib mainloop")
        self.glib_loop.run()  # type: ignore[attr-defined]

    def printer_setup_body(self):
        self.printer.setup()
        print("Overriding printer settings")
        self.printer.hw.config.calibrated = True
        self.printer.hw.config.showWizard = False
        self.printer.hw.config.fanCheck = False
        self.printer.hw.config.coverCheck = False
        self.printer.hw.config.resinSensor = False

    def fake_save_path(self):
        return Path(self.temp)

    async def async_tear_down(self):
        loop = asyncio.get_running_loop()
        # Run all teardown parts in parallel. Some may block or fail
        with concurrent.futures.ThreadPoolExecutor() as pool:
            tasks = [
                loop.run_in_executor(pool, self.printer.stop),
                loop.run_in_executor(pool, self.rauc_mocks.unpublish),
                loop.run_in_executor(pool, self.glib_loop.quit),
                loop.run_in_executor(pool, self.printer0.unpublish),
                loop.run_in_executor(pool, self.standard0.unpublish),
                loop.run_in_executor(pool, self.admin0_dbus.unpublish),
            ]
        await asyncio.gather(*tasks)


def run_virtual():
    Virtual()()


if __name__ == "__main__":
    run_virtual()
