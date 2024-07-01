# This file is part of the SLA firmware
# Copyright (C) 2020-2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from slafw.libPrinter import Printer
from slafw.admin.control import AdminControl
from slafw.admin.items import AdminAction
from slafw.admin.menu import AdminMenu
from slafw.admin.menus.settings.fans import FansMenu
from slafw.admin.menus.settings.uvled import UVLedMenu
from slafw.admin.menus.settings.hardware import HardwareSettingsMenu
from slafw.admin.menus.settings.exposure import ExposureSettingsMenu
from slafw.admin.menus.settings.hwconfig import HwConfigMenu
from slafw.admin.menus.settings.backup import BackupConfigMenu


class SettingsRoot(AdminMenu):
    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control)
        self.add_back()
        self.add_items(
            (
                AdminAction("Fans", lambda: self.enter(FansMenu(self._control, printer)), "fan_color"),
                AdminAction("UV LED", lambda: self.enter(UVLedMenu(self._control, printer)), "led_set_replacement"),
                AdminAction("Hardware setup", lambda: self.enter(HardwareSettingsMenu(self._control, printer)), "firmware-icon"),
                AdminAction("Exposure setup", lambda: self.enter(ExposureSettingsMenu(self._control, printer)), "change_color"),
                AdminAction("All config items", lambda: self.enter(HwConfigMenu(self._control, printer)), "edit_white"),
                AdminAction("Backup config", lambda: self.enter(BackupConfigMenu(self._control, printer)), "save_color"),
            ),
        )
