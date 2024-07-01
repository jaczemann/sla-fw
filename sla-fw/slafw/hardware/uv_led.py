# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from abc import abstractmethod, ABC
from dataclasses import dataclass
from functools import cached_property
from typing import Callable, Dict, Any

from PySignal import Signal

from slafw.hardware.component import HardwareComponent


@dataclass(eq=False)
class UvLedParameters:
    min_pwm: int
    max_pwm: int
    safe_default_pwm: int
    intensity_error_threshold: int
    param_p: float


class UVLED(HardwareComponent, ABC):
    def __init__(self):
        super().__init__("UV LED")
        self.usage_s_changed = Signal()

    @abstractmethod
    def on(self):
        """
        Permanently turn on UV
        """

    @abstractmethod
    def off(self):
        """
        Permanently turn off UV
        """

    @abstractmethod
    def pulse(self, time_ms: int):
        """
        Make a UV pulse

        Turn UV on and off after a specified amount of time. This is supposed
        to do a precise timing of the pulse length.
        """

    @property
    @abstractmethod
    def active(self) -> bool:
        """
        Whether UV LED is on
        """

    @property
    @abstractmethod
    def pulse_remaining(self) -> int:
        """
        Remaining pulse time in ms
        """

    @property
    @abstractmethod
    def usage_s(self) -> int:
        """
        How long has the UV LED been used
        """

    @abstractmethod
    def save_usage(self):
        """
        Store usage to permanent storage
        """

    @abstractmethod
    def clear_usage(self):
        """
        Clear usage

        Use this when UV LED is replaced
        """

    @abstractmethod
    async def selftest(self, callback: Callable[[float], None] = None) -> Dict[str, Any]:
        """
        Perform a selftest

        This runs a selftest with optional progress reporting callback. If a problem is discovered
        an exception is raised. A dictionary describing hardware state is returned.
        """

    @property
    @abstractmethod
    def pwm(self) -> int:
        """
        Read current PWM
        """

    @pwm.setter
    @abstractmethod
    def pwm(self, value: int):
        """
        Set PWM
        """

    @property
    @abstractmethod
    def max_pwm(self) -> int:
        """
        Maximal supported PWM value
        """

    @property
    @abstractmethod
    def info(self) -> Dict[str, Any]:
        """
        UV LED description dictionary, used in log summary
        """

    @cached_property
    @abstractmethod
    def parameters(self) -> UvLedParameters:
        """
        UV LED related parameters
        """

    @cached_property
    def serial(self) -> str:
        """
        UV LED electronic serial number
        """
