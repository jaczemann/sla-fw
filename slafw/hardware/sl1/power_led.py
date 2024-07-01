# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from slafw.motion_controller.sl1_controller import MotionControllerSL1
from slafw.errors.errors import MotionControllerException
from slafw.hardware.power_led import PowerLedActions, PowerLed


class PowerLedSL1(PowerLed):

    def __init__(self, mcc: MotionControllerSL1):
        super().__init__()
        self._mcc = mcc
        self._error_level_counter = 0
        self._warn_level_counter = 0
        self._modes = {
            # (mode, speed)
            PowerLedActions.Normal: (1, 2),
            PowerLedActions.Warning: (2, 10),
            PowerLedActions.Error: (3, 15),
            PowerLedActions.Off: (3, 64)
        }

    @property
    def mode(self) -> PowerLedActions:
        result = PowerLedActions.Unspecified
        try:
            mode = self._mcc.doGetInt("?pled")
            speed = self._mcc.doGetInt("?pspd")
            for k, v in self._modes.items():
                if v[0] == mode and v[1] == speed:
                    result = k
        except MotionControllerException:
            self.logger.exception("Failed to read power led pwm")
        return result

    @mode.setter
    def mode(self, value: PowerLedActions):
        m, s = self._modes[value]
        try:
            self._mcc.do("!pled", m)
            self._mcc.do("!pspd", s)
        except MotionControllerException:
            self.logger.exception("Failed to read power led pwm")

    @property
    def intensity(self):
        try:
            pwm = self._mcc.do("?ppwm")
            return int(pwm) * 5
        except MotionControllerException:
            self.logger.exception("Failed to read power led pwm")
            return -1

    @intensity.setter
    def intensity(self, pwm: int):
        try:
            self._mcc.do("!ppwm", int(pwm / 5))
        except MotionControllerException:
            self.logger.exception("Failed to set power led pwm")
