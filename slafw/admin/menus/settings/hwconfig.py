# This file is part of the SLA firmware
# Copyright (C) 2020-2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Collection

from slafw.libPrinter import Printer
from slafw.admin.control import AdminControl
from slafw.admin.items import AdminIntValue, AdminFloatValue, AdminBoolValue, AdminItem
from slafw.admin.menus.settings.base import SettingsMenu
from slafw.configs.value import IntValue, FloatValue, BoolValue


class HwConfigMenu(SettingsMenu):
    NAME_STEP_MAP = {
        "fan1Rpm": 100,
        "fan2Rpm": 100,
        "fan3Rpm": 100,
    }

    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control, printer)
        self._config = printer.hw.config
        self._warning = self.add_label(
                "<b>WARNING! This is unrestricted raw edit of all config values.</b>",
                "warning_white")
        self.add_items(self._get_config_items())

    def _get_config_items(self) -> Collection[AdminItem]:
        for name, value in self._config.get_values().items():
            if isinstance(value, IntValue):
                step = self.NAME_STEP_MAP.get(name, 1)
                yield AdminIntValue.from_value(name, self._temp, name, step, "edit_white")
            if isinstance(value, FloatValue):
                step = self.NAME_STEP_MAP.get(name, 0.1)
                yield AdminFloatValue.from_value(name, self._temp, name, step, "edit_white")
            if isinstance(value, BoolValue):
                yield AdminBoolValue.from_value(name, self._temp, name, "edit_white")
