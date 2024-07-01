# This file is part of the SLA firmware
# Copyright (C) 2020-2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from slafw.libPrinter import Printer
from slafw.admin.control import AdminControl
from slafw.admin.items import AdminIntValue, AdminBoolValue
from slafw.admin.menus.settings.base import SettingsMenu


class HardwareSettingsMenu(SettingsMenu):
    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control, printer)
        self.add_items(
            (
                AdminBoolValue.from_value("Fan check", self._temp, "fanCheck", "fan_color"),
                AdminBoolValue.from_value("Cover check", self._temp, "coverCheck", "cover_color"),
                AdminBoolValue.from_value("MC version check", self._temp, "MCversionCheck", "firmware-icon"),
                AdminBoolValue.from_value("Use resin sensor", self._temp, "resinSensor", "refill_color"),
                AdminBoolValue.from_value("Auto power off", self._temp, "autoOff", "turn_off_color"),
                AdminBoolValue.from_value("Mute (no beeps)", self._temp, "mute", "wifi_strength_0"),
                AdminIntValue.from_value("Screw [mm/rot]", self._temp, "screwMm", 1, "calibration_color"),
                AdminIntValue.from_value("Tilt height [usteps]", self._temp, "tiltHeight", 1, "tank_reset_color"),
                AdminIntValue.from_value(
                    "Measuring moves count",
                    self._temp,
                    "measuringMoves",
                    1,
                    "move_resin_tank_color"),
                AdminIntValue.from_value("Power LED intensity", self._temp, "pwrLedPwm", 1, "brightness_color"),
            )
        )
