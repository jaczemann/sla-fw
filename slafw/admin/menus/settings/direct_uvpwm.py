# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import json
from datetime import datetime
from threading import Thread
from dataclasses import asdict
from functools import partial

from slafw import defines
from slafw.libPrinter import Printer
from slafw.admin.control import AdminControl
from slafw.admin.items import AdminAction, AdminBoolValue, AdminIntValue, AdminLabel
from slafw.admin.safe_menu import SafeAdminMenu
from slafw.admin.menus.dialogs import Info, Wait, Error
from slafw.errors.errors import DisplayTransmittanceNotValid, CalculatedUVPWMNotInRange
from slafw.functions.system import compute_uvpwm
from slafw.functions import generate
from slafw.libUvLedMeterMulti import UvLedMeterMulti
from slafw.hardware.power_led_action import WarningAction


class DirectPwmSetMenu(SafeAdminMenu):
    # pylint: disable=too-many-instance-attributes
    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control)
        self._printer = printer
        self._temp = self._printer.hw.config.get_writer()
        self._run = True
        self._status = "<b>UV meter disconnected<b>"
        self._data = None
        self._uv_pwm_print = self._temp.uvPwmPrint

        self.add_back()
        uv_pwm_item = AdminIntValue.from_value("UV LED PWM", self._temp, "uvPwm", 1, "uv_calibration")
        uv_pwm_item.changed.connect(self._uv_pwm_changed)
        uv_pwm_tune_item = AdminIntValue.from_value("UV LED PWM fine tune", self._temp, "uvPwmTune", 1, "change_color")
        uv_pwm_tune_item.changed.connect(self._uv_pwm_changed)
        self.uv_pwm_print_item = AdminLabel.from_property(self, DirectPwmSetMenu.uv_pwm_print, "system_info_color")
        self.add_items(
            (
                AdminBoolValue.from_value("UV LED", self, "uv_led", "led_set_replacement"),
                AdminAction("Open screen", self.open, "print_color"),
                AdminAction("Close screen", self.close, "disabled_color"),
                AdminAction("Calculate PWM from display transmittance", self.calculate_pwm, "statistics_color"),
                self.uv_pwm_print_item,
                uv_pwm_item,
                uv_pwm_tune_item,
                AdminLabel.from_property(self, DirectPwmSetMenu.status, "system_info_color"),
                AdminAction("Show measured data", partial(self.show_calibration), "logs-icon"),
            )
        )
        self._thread = Thread(target=self._measure)

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value: str):
        self._status = value

    def on_enter(self):
        self._thread.start()
        self.enter(Wait(self._control, self._do_prepare))

    def on_leave(self):
        self._run = False
        self._printer.hw_all_off()
        self._printer.hw.uv_led.save_usage()
        self._temp.commit()
        if self._data:
            file_path = defines.wizardHistoryPathFactory / f"{defines.manual_uvc_filename}.{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json"
            with file_path.open("w") as file:
                json.dump(asdict(self._data), file, indent=2, sort_keys=True)
        self._thread.join()

    def _measure(self):
        meter = UvLedMeterMulti()
        connected = False
        while self._run:
            if connected:
                if meter.read():
                    self._data = meter.get_data(plain_mean=True)
                    self._data.uvFoundPwm = self._uv_pwm_print
                    self.status = (
                        f"<b>ø:{self._data.uvMean:.1f} σ:{self._data.uvStdDev:.1f} {self._data.uvTemperature:.1f}°C<b>"
                    )
                else:
                    self.status = "<b>UV meter disconnected<b>"
                    connected = False
            elif meter.connect():
                self.status = "<b>UV meter connected<b>"
                connected = True
        meter.close()

    @SafeAdminMenu.safe_call
    def show_calibration(self):
        generate.uv_calibration_result(asdict(self._data) if self._data else None, None, defines.fullscreenImage)
        self._control.fullscreen_image()

    @SafeAdminMenu.safe_call
    def _do_prepare(self, status: AdminLabel):
        with WarningAction(self._printer.hw.power_led):
            status.set("<b>Tilt is going to level<b>")
            self._printer.hw.tilt.actual_profile = self._printer.hw.tilt.profiles.homingFast
            self._printer.hw.tilt.sync_ensure()
            self._printer.hw.tilt.actual_profile = self._printer.hw.tilt.profiles.move8000
            self._printer.hw.tilt.move_ensure(self._printer.hw.config.tiltHeight)  # move to level

        status.set("<b>Tilt leveled<b>")
        self._printer.hw.start_fans()
        self._printer.hw.uv_led.pwm = self._uv_pwm_print
        self._printer.hw.uv_led.on()
        self._printer.exposure_image.open_screen()

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

    @property
    def uv_pwm_print(self) -> str:
        return "<b>Final UV PWM value: " + str(self._uv_pwm_print) + "</b>"

    @uv_pwm_print.setter
    def uv_pwm_print(self, value):
        self._uv_pwm_print = value

    @SafeAdminMenu.safe_call
    def open(self):
        self._printer.exposure_image.open_screen()

    @SafeAdminMenu.safe_call
    def close(self):
        self._printer.exposure_image.blank_screen()

    def _uv_pwm_changed(self):
        # TODO: simplify work with config and config writer
        self.uv_pwm_print_item.set_value(self._temp.uvPwm + self._temp.uvPwmTune)
        self._printer.hw.uv_led.pwm = self._uv_pwm_print

    def calculate_pwm(self):
        try:
            pwm = compute_uvpwm(self._printer.hw)
        except DisplayTransmittanceNotValid as exception:
            self._control.enter(
                Error(self._control, text=f"Display transmittance {exception.transmittance} is not valid", pop=1)
            )
            return
        except CalculatedUVPWMNotInRange as e:
            self._control.enter(
                Error(self._control, text=f"Calculated value {e.pwm} is not in range <{e.pwm_min},{e.pwm_max}>", pop=1)
            )
            return

        self._temp.uvPwm = pwm
        self._uv_pwm_changed()
        self._control.enter(Info(self._control, f"Calculated PWM is {pwm}"))
