# This file is part of the SLA firmware
# Copyright (C) 2021-2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from functools import partial

from slafw import defines
from slafw.admin.control import AdminControl
from slafw.admin.items import AdminAction, AdminLabel
from slafw.admin.menus.dialogs import Info, Confirm, Wait
from slafw.admin.safe_menu import SafeAdminMenu
from slafw.errors.errors import NotConnected
from slafw.libPrinter import Printer
from slafw.states.printer import PrinterState


class MotionControllerMenu(SafeAdminMenu):
    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control)
        self._printer = printer

        self.add_back()
        self.add_items(
            (
                AdminAction("Flash MC", self.flash_mc, "firmware-icon"),
                AdminAction("Erase MC EEPROM", self.erase_mc_eeprom, "delete_small_white"),
                AdminAction("MC2Net (bootloader)", self.mc2net_boot, "remote_small_white"),
                AdminAction("MC2Net (firmware)", self.mc2net_firmware, "remote_control_color"),
            ),
        )

    def flash_mc(self):
        self._control.enter(
            Confirm(self._control, self._do_flash_mc, text="This will overwrite the motion controller firmware.")
        )

    def _do_flash_mc(self):
        self._control.enter(Wait(self._control, self._do_flash_mc_body))

    def _do_flash_mc_body(self, status: AdminLabel):
        status.set("Forced update of the motion controller firmware")
        self._printer.set_state(PrinterState.UPDATING_MC)
        self._printer.hw.flashMC()
        self._printer.hw.eraseEeprom()
        self._printer.hw.initDefaults()
        self._printer.set_state(PrinterState.UPDATING_MC, active=False)
        self._control.enter(Info(self._control, text="Motion controller flashed", pop=2))

    def erase_mc_eeprom(self):
        self._control.enter(
            Confirm(
                self._control,
                self._do_erase_mc_eeprom,
                text="This will erase all profiles\nand other motion controller settings.",
            )
        )

    def _do_erase_mc_eeprom(self):
        self._control.enter(Wait(self._control, self._do_erase_mc_eeprom_body))

    def _do_erase_mc_eeprom_body(self, status: AdminLabel):
        status.set("Erasing EEPROM")
        self._printer.set_state(PrinterState.UPDATING_MC)
        self._printer.hw.eraseEeprom()
        self._printer.hw.initDefaults()
        self._printer.set_state(PrinterState.UPDATING_MC, active=False)
        self._control.enter(Info(self._control, text="Motion controller eeprom erased.", pop=2))

    def mc2net_boot(self):
        self._control.enter(
            Confirm(
                self._control,
                partial(self._do_mc2net, True),
                text="This will freeze the printer\nand connect the MC bootloader to TCP port.",
            )
        )

    def mc2net_firmware(self):
        self._control.enter(
            Confirm(
                self._control,
                partial(self._do_mc2net, False),
                text="This will connect the motion controller to TCP port.",
            )
        )

    @SafeAdminMenu.safe_call
    def _do_mc2net(self, bootloader=False):
        ip = self._printer.inet.ip
        if ip is None:
            raise NotConnected("Cannot start mc net connection when not connected")

        self._printer.hw.mcc.start_debugging(bootloader=bootloader)

        self._control.enter(
            Info(
                self._control,
                headline="Listening for motion controller debugging connection.",
                text=f"Serial line is redirected to {ip}:{defines.mc_debug_port}.\n\n"
                "Press continue to use the printer. The debugging will\n"
                "begin with new connection and will end as soon as\n"
                "the connection terminates.",
                pop=2,
            )
        )
