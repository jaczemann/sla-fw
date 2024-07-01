# This file is part of the SLA firmware
# Copyright (C) 2020-2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from slafw.libPrinter import Printer
from slafw.admin.control import AdminControl
from slafw.admin.items import AdminAction
from slafw.admin.menu import AdminMenu
from slafw.admin.menus.firmware.logging import LoggingMenu
from slafw.admin.menus.firmware.net_update import NetUpdate
from slafw.admin.menus.firmware.system_info import SystemInfoMenu
from slafw.admin.menus.firmware.system_tools import SystemToolsMenu
from slafw.admin.menus.firmware.tests import FirmwareTestMenu


class FirmwareRoot(AdminMenu):
    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control)

        self.add_back()
        self.add_items(
            (
                AdminAction("Net update", lambda: self.enter(NetUpdate(self._control, printer)), "network-icon"),
                AdminAction("Logging", lambda: self.enter(LoggingMenu(self._control, printer)), "logs-icon"),
                AdminAction("System tools", lambda: self.enter(SystemToolsMenu(self._control, printer)), "about_us_color"),
                AdminAction("System information", lambda: self.enter(SystemInfoMenu(self._control, printer)), "system_info_color"),
                AdminAction("Firmware tests", lambda: self.enter(FirmwareTestMenu(self._control, printer)), "limit_color"),
            ),
        )
