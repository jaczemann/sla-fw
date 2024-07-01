# This file is part of the SLA firmware
# Copyright (C) 2020-2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from slafw.libPrinter import Printer
from slafw.admin.control import AdminControl
from slafw.admin.items import AdminAction
from slafw.admin.menus.firmware.admin_api_test import ApiTestMenu
from slafw.admin.menus.firmware.errors_test import SL1CodesMenu
from slafw.admin.menus.firmware.wizards_test import WizardsTestMenu
from slafw.admin.safe_menu import SafeAdminMenu
from slafw.errors.errors import UnknownPrinterModel


class FirmwareTestMenu(SafeAdminMenu):
    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control)
        self.logger = logging.getLogger(__name__)
        self._printer = printer

        self.add_back()
        self.add_items(
            (
                AdminAction("SL1Codes test", lambda: self.enter(SL1CodesMenu(self._control, self._printer)), "error_small_white"),
                AdminAction("Wizards test", lambda: self.enter(WizardsTestMenu(self._control, self._printer)), "wizard_color"),
                AdminAction("Admin API test", lambda: self.enter(ApiTestMenu(self._control))),
                AdminAction("Simulate disconnected display", self.simulate_disconnected_display, "error_small_white"),
            )
        )

    def simulate_disconnected_display(self):
        self._printer.enter_fatal_error(UnknownPrinterModel())
