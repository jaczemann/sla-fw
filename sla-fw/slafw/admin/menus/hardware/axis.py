# This file is part of the SLA firmware
# Copyright (C) 2021-2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from time import sleep

from slafw.admin.control import AdminControl
from slafw.admin.items import AdminAction, AdminLabel
from slafw.admin.menus.dialogs import Wait, Error
from slafw.admin.menus.hardware.profiles import Profiles
from slafw.admin.safe_menu import SafeAdminMenu
from slafw.libPrinter import Printer
from slafw.errors.errors import TiltHomeFailed, TowerHomeFailed
from slafw.hardware.power_led_action import WarningAction
from slafw.hardware.axis import Axis


class AxisMenu(SafeAdminMenu):
    def __init__(self, control: AdminControl, printer: Printer, axis: Axis):
        super().__init__(control)
        self._printer = printer
        self._axis = axis

        self.add_back()
        self.add_items(
            (
                AdminAction(f"Release {axis.name} motor", self.release_motor, "disable_steppers_color"),
                AdminAction(f"Home {axis.name}", self.home, "home_small_white"),
                AdminAction(f"Move {axis.name} to calibrated position", self.config_position, "finish_white"),
                AdminAction(f"Manual {axis.name} move", self.manual_move, "control_color"),
                AdminAction(
                    f"{axis.name.capitalize()} profiles",
                    lambda: self.enter(Profiles(self._control, printer, axis.profiles, axis)),
                    "steppers_color"
                 ),
                AdminAction("Home calibration", self.home_calib, "calibration_color"),
                AdminAction(f"Test {axis.name}", self.test, "limit_color"),
            )
        )

    def _move_to_home(self, status: AdminLabel):
        if self._axis.synced:
            status.set(f"Moving {self._axis.name} to home position")
            self._axis.actual_profile = self._axis.profiles.homingFast    # type: ignore
            self._axis.move_ensure(self._axis.home_position)
        else:
            status.set(f"Homing {self._axis.name}")
            try:
                self._axis.sync_ensure()
            except (TiltHomeFailed, TowerHomeFailed):
                self._control.enter(Error(self._control, text=f"Failed to home {self._axis.name}"))
                return False
            status.set(f"Home {self._axis.name} done")
        return True

    def _move_to_home_opposite(self, status: AdminLabel):
        self._axis.actual_profile = self._axis.profiles.homingFast    # type: ignore
        if self._axis.home_position:
            status.set(f"Moving {self._axis.name} to minimal position")
            self._axis.move_ensure(self._axis.minimal_position)
        else:
            status.set(f"Moving {self._axis.name} to configured position")
            self._axis.move_ensure(self._axis.config_height_position)

    @SafeAdminMenu.safe_call
    def release_motor(self):
        self._axis.release()

    @SafeAdminMenu.safe_call
    def home(self):
        self._control.enter(Wait(self._control, self._do_home))

    def _do_home(self, status: AdminLabel):
        with WarningAction(self._printer.hw.power_led):
            self._move_to_home(status)

    @SafeAdminMenu.safe_call
    def config_position(self):
        self._control.enter(Wait(self._control, self._do_config_position))

    def _do_config_position(self, status: AdminLabel):
        with WarningAction(self._printer.hw.power_led):
            if not self._axis.synced:
                if not self._move_to_home(status):
                    return
            self._move_to_home_opposite(status)

    @SafeAdminMenu.safe_call
    def test(self):
        self._control.enter(Wait(self._control, self._do_test))

    def _do_test(self, status: AdminLabel):
        with WarningAction(self._printer.hw.power_led):
            if self._move_to_home(status):
                self._printer.hw.beepEcho()
                sleep(1)
                self._move_to_home_opposite(status)
                self._printer.hw.beepEcho()
                sleep(1)
                self._move_to_home(status)

    @SafeAdminMenu.safe_call
    def home_calib(self):
        self.enter(Wait(self._control, self._do_home_calib))

    def _do_home_calib(self, status: AdminLabel):
        status.set("Home calibration")
        with WarningAction(self._printer.hw.power_led):
            self._axis.home_calibrate_wait()

    @SafeAdminMenu.safe_call
    def manual_move(self):
        getattr(self._control, f"{self._axis.name}_moves")()
