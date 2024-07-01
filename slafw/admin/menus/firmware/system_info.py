# This file is part of the SLA firmware
# Copyright (C) 2021-2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import datetime, timedelta
from threading import Thread
from time import sleep

import psutil

from slafw import defines
from slafw.admin.control import AdminControl
from slafw.admin.items import AdminAction
from slafw.admin.menu import AdminMenu
from slafw.configs.stats import TomlConfigStats
from slafw.libPrinter import Printer


class SystemInfoMenu(AdminMenu):
    # pylint: disable = too-many-instance-attributes
    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control)
        self._printer = printer
        self._fans = {}

        self.add_back()

        self.system_time = self.add_label(None, "time_color")
        self.system_uptime = self.add_label(None, "time_color")
        self.os_version = self.add_label(None, "firmware-icon")
        self.a64_sn = self.add_label(None, "firmware-icon")
        self.emmc_sn = self.add_label(None, "firmware-icon")
        self.mc_sn = self.add_label(None, "firmware-icon")
        self.mc_sw = self.add_label(None, "firmware-icon")
        self.mc_rev = self.add_label(None, "firmware-icon")
        self.eth_mac = self.add_label(None, "firmware-icon")
        self.expo_panel_sn = self.add_label(None, "display_replacement")
        self.expo_panel_resolution = self.add_label(None, "display_replacement")
        self.expo_panel_transmittance = self.add_label(None, "display_replacement")
        self.printer_model = self.add_label(None, "cover_color")
        self.net_state = self.add_label(None, "lan_color")
        self.net_dev = self.add_label(None, "lan_color")
        self.http_digest_password = self.add_label(None, "key_color")
        self.tilt_times = self.add_label(None, "tank_reset_color")
        self.resin_sensor = self.add_label(None, "refill_color")
        self.cover = self.add_label(None, "cover_color")
        self.cpu_temp = self.add_label(None, "limit_color")
        self.uv_led_temp = self.add_label(None, "limit_color")
        self.ambient_temp = self.add_label(None, "limit_color")
        for fidx in self._printer.hw.fans.keys():
            self._fans[fidx] = self.add_label(None, "fan_color")
        self.uv_led = self.add_label(None, "led_set_replacement")
        self.uv_counter = self.add_label(None, "led_set_replacement")
        self.display_counter = self.add_label(None, "display_replacement")
        self.started_projects = self.add_label(None, "testtube")
        self.finished_projects = self.add_label(None, "testtube")
        self.total_layers = self.add_label(None, "statistics_color")
        self.total_print_time = self.add_label(None, "statistics_color")
        self.total_resin = self.add_label(None, "refill_color")

        self.add_item(AdminAction("User sysinfo", self._control.sysinfo, "system_info_color"))

        self._running = True
        self._thread = Thread(target=self._run)

    def on_enter(self):
        self._thread.start()

    def on_leave(self):
        self._running = False
        self._thread.join()

    def _run(self):
        self.os_version.set(f"OS version: {self._printer.hw.system_version}")
        self.a64_sn.set(f"A64 serial: {self._printer.hw.cpuSerialNo}")
        self.emmc_sn.set(f"eMMC serial: {self._printer.hw.emmc_serial}")
        self.mc_sn.set(f"MC serial: {self._printer.hw.mcSerialNo}")
        self.mc_sw.set(f"MC SW version: {self._printer.hw.mcFwVersion}")
        self.mc_rev.set(f"MC revision: {self._printer.hw.mcBoardRevision}")
        self.eth_mac.set(f"Hardcoded eth MAC: {self._printer.hw.ethMac}")
        self.expo_panel_sn.set(f"Exposure panel serial: {self._printer.hw.exposure_screen.serial_number}")
        self.expo_panel_resolution.set(f"Exposure panel resolution: {self._printer.hw.exposure_screen.parameters.width_px}x{self._printer.hw.exposure_screen.parameters.height_px} px")
        self.expo_panel_transmittance.set(f"Exposure panel transmittance: {self._printer.hw.exposure_screen.transmittance} %")
        self.printer_model.set(f"Printer model: {self._printer.hw.printer_model.name}")
        self.http_digest_password.set(f"HTTP digest password: {self._printer.http_digest_password}")
        self.uv_counter.set(f"UV LED counter: {timedelta(seconds=self._printer.hw.uv_led.usage_s)}")
        self.display_counter.set(f"Display counter: {timedelta(seconds=self._printer.hw.exposure_screen.usage_s)}")
        sys_stats = TomlConfigStats(defines.statsData, self._printer.hw)
        self.started_projects.set(f"Total started projects: {sys_stats['started_projects']}")
        self.finished_projects.set(f"Total finished projects: {sys_stats['finished_projects']}")
        self.total_layers.set(f"Total layers: {sys_stats['layers']}")
        self.total_print_time.set(f"Total print time: {timedelta(seconds=sys_stats['total_seconds'])}")
        self.total_resin.set(f"Total resin used: {sys_stats['total_resin']} ml")

        self._printer.hw.resinSensor(True)
        loop = 5
        while self._running:
            loop += 1
            if loop >= 5:
                self.logger.debug("Updating system information")
                self.system_time.set(f"System time: {datetime.now().strftime('%x %X')}")
                self.system_uptime.set(f"System uptime: {':'.join(str(datetime.now() - datetime.fromtimestamp(psutil.boot_time())).split('.')[:1])}")
                self.net_state.set(f"Network state: {'online' if self._printer.inet.ip else 'offline'}")
                self.net_dev.set(f"Net devices: {self._printer.inet.devices}")
                self.resin_sensor.set(f"Resin sensor triggered: {self._printer.hw.getResinSensorState()}")
                self.cover.set(f"Cover closed: {self._printer.hw.isCoverClosed()}")
                self.cpu_temp.set(f"CPU temperature: {self._printer.hw.cpu_temp.value}")
                self.uv_led_temp.set(f"UV LED temperature: {self._printer.hw.uv_led_temp.value}")
                self.ambient_temp.set(f"Ambient temperature: {self._printer.hw.ambient_temp.value}")
                for fidx, fan in self._printer.hw.fans.items():
                    self._fans[fidx].set(f"{fan.name} fan RPM: {fan.rpm}")
                uv_led_info_list = [f"<li>{key}: {value}</li>" for key, value in self._printer.hw.uv_led.info.items()]
                self.uv_led.set(f"UV LED: <ul>{''.join(uv_led_info_list)}</ul>")
                loop = 0
            sleep(.1)

        self._printer.hw.resinSensor(False)
