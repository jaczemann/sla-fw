# This file is part of the SLA firmware
# Copyright (C) 2020-2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from slafw.libPrinter import Printer
from slafw.hardware.axis import Axis
from slafw.admin.control import AdminControl
from slafw.admin.items import AdminAction
from slafw.admin.menu import AdminMenu
from slafw.admin.menus.hardware.tests import HardwareTestMenu
from slafw.admin.menus.hardware.display import ExposureDisplayMenu
from slafw.admin.menus.hardware.motion_controller import MotionControllerMenu
from slafw.admin.menus.hardware.axis import AxisMenu


class HardwareRoot(AdminMenu):
    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control)
        self._printer = printer
        items = [
                AdminAction(
                    "Exposure display",
                    lambda: self.enter(ExposureDisplayMenu(self._control, printer)),
                    "display_replacement"
                )]
        for axis in printer.hw.axes.values():
            items.append(
                AdminAction(
                    axis.name.capitalize(),
                    self._get_callback(axis),
                    f"{axis.name}_sensitivity_color"
                ))
        items.append(
                AdminAction(
                    "Motion controller",
                    lambda: self.enter(MotionControllerMenu(self._control, printer)),
                    "control_color"
                ))
        items.append(
                AdminAction(
                    "Hardware tests",
                    lambda: self.enter(HardwareTestMenu(self._control, printer)),
                    "limit_color"
                ))

        self.add_back()
        self.add_items(items)

    def _get_callback(self, axis: Axis):
        return lambda: self.enter(AxisMenu(self._control, self._printer, axis))
