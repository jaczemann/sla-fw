# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from functools import cached_property
from typing import Dict, Any, Callable

from slafw.hardware.uv_led import UVLED, UvLedParameters


class MockUVLED(UVLED):
    def __init__(self):
        super().__init__()
        self._usage_s = 6912
        self._pwm = 250

    def on(self):
        pass

    def off(self):
        pass

    def pulse(self, time_ms: int):
        self._usage_s += time_ms / 1000
        self.usage_s_changed.emit(self._usage_s)

    @property
    def active(self) -> bool:
        return False

    @property
    def pulse_remaining(self) -> int:
        return 0

    @property
    def usage_s(self) -> int:
        return round(self._usage_s)

    def save_usage(self):
        pass

    def clear_usage(self):
        self._usage_s = 0

    @property
    def pwm(self) -> int:
        return self._pwm

    @pwm.setter
    def pwm(self, value: int):
        self._pwm = value

    @property
    def max_pwm(self) -> int:
        return 250

    @property
    def info(self) -> Dict[str, Any]:
        return {"mock uv led into": 42}

    @cached_property
    def parameters(self) -> UvLedParameters:
        return UvLedParameters(
            min_pwm=1,
            max_pwm=250,
            safe_default_pwm=123,
            intensity_error_threshold=5,
            param_p=0.75,
        )

    async def selftest(self, callback: Callable[[float], None] = None) -> Dict[str, Any]:
        return {
            "uvPwm": self.pwm,
            "mock selftest result": 42,
        }
