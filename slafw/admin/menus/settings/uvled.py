# This file is part of the SLA firmware
# Copyright (C) 2020-2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from slafw.libPrinter import Printer
from slafw.admin.control import AdminControl
from slafw.admin.items import AdminIntValue, AdminBoolValue, AdminAction
from slafw.admin.safe_menu import SafeAdminMenu
from slafw.admin.menus.dialogs import Info, Confirm
from slafw.admin.menus.settings.base import SettingsMenu
from slafw.admin.menus.settings.direct_uvpwm import DirectPwmSetMenu


class UVLedMenu(SettingsMenu):

    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control, printer)
        self._printer = printer

        self._uv_pwm_print = self._temp.uvPwmPrint

        uv_pwm_item = AdminIntValue.from_value("UV LED PWM", self._temp, "uvPwm", 1, "uv_calibration")
        uv_pwm_item.changed.connect(self._uv_pwm_changed)
        uv_pwm_tune_item = AdminIntValue.from_value("UV LED PWM fine tune", self._temp, "uvPwmTune", 1, "change_color")
        uv_pwm_tune_item.changed.connect(self._uv_pwm_changed)

        self.add_items(
            (
                AdminAction("Direct UV PWM settings", self.enter_direct_uvpwm, "display_test_color"),
                AdminBoolValue.from_value("UV LED", self, "uv_led", "led_set_replacement"),
                uv_pwm_item,
                uv_pwm_tune_item,
                AdminIntValue.from_value("UV calibration warm-up [s]", self._temp, "uvWarmUpTime", 1, "exposure_times_color"),
                AdminIntValue.from_value("UV calibration intensity", self._temp, "uvCalibIntensity", 1, "brightness_color"),
                AdminIntValue.from_value("UV calibration min. intensity edge", self._temp, "uvCalibMinIntEdge", 1, "brightness_color"),
            )
        )
        if self._printer.hw.printer_model.options.has_booster: # type: ignore[attr-defined]
            self.add_item(AdminAction("Write PWM to booster board", self._write_to_booster, "firmware-icon"))

    def on_leave(self):
        super().on_leave()
        self._printer.hw.uv_led.save_usage()

    @property
    def uv_led(self) -> bool:
        return self._printer.hw.uv_led.active

    @uv_led.setter
    def uv_led(self, value: bool):
        if value:
            self._printer.hw.start_fans()
            self._printer.hw.uv_led.pwm = self._uv_pwm_print
            self._printer.hw.uv_led.on()
        else:
            self._printer.hw.stop_fans()
            self._printer.hw.uv_led.off()

    @SafeAdminMenu.safe_call
    def _write_to_booster(self):
        self._printer.hw.uv_led.pwm = self._uv_pwm_print
        self._printer.hw.sl1s_booster.save_permanently()
        self._control.enter(Info(self._control, "PWM value was written to the booster board"))

    def _uv_pwm_changed(self):
        # TODO: simplify work with config and config writer
        self._uv_pwm_print = self._temp.uvPwm + self._temp.uvPwmTune
        self._printer.hw.uv_led.pwm = self._uv_pwm_print

    def enter_direct_uvpwm(self):
        self._control.enter(
            Confirm(
                self._control,
                self._do_enter_direct_uvpwm,
                headline="Do you really want to enter the menu?",
                text="It will turn on the UV LED, open the exposure display\n"
                "and move the tilt. Do not enter during active print job.",
            )
        )

    def _do_enter_direct_uvpwm(self):
        self._control.enter(DirectPwmSetMenu(self._control, self._printer))
