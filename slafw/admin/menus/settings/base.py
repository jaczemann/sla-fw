# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from slafw.libPrinter import Printer
from slafw.admin.control import AdminControl
from slafw.admin.menu import AdminMenu


class SettingsMenu(AdminMenu):
    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control)
        self._temp = printer.hw.config.get_writer()
        self.add_back()

    def on_leave(self):
        self._temp.commit()
