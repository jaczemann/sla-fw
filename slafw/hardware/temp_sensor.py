# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from abc import ABC, abstractmethod
from typing import Optional

from PySignal import Signal

from slafw.hardware.component import HardwareComponent


class TempSensor(HardwareComponent, ABC):
    """
    Abstract temperature sensor
    """

    # pylint: disable = too-many-instance-attributes
    # pylint: disable = too-many-arguments

    VALUE_LOGGING_THRESHOLD_DEG_C = 1

    def __init__(
        self,
        name: str,
        minimal: Optional[float] = None,
        maximal: Optional[float] = None,
        critical: Optional[float] = None,
        hysteresis: float = 0,
    ):
        super().__init__(name)
        self._min = minimal
        self._max = maximal
        self._critical = critical
        self._hysteresis = hysteresis
        self._name = "UNKNOWN"
        self.value_changed = Signal()
        self.value_changed.connect(self._on_value_change)
        self.overheat_changed = Signal()
        self._overheat = False
        self._last_logged_temp: Optional[float] = None

    @property
    @abstractmethod
    def value(self) -> float:
        """
        Temperature [°C]
        """

    @property
    def min(self) -> Optional[float]:
        """
        Configured minimal temperature [°C] for cooling management
        """
        return self._min

    @property
    def max(self) -> Optional[float]:
        """
        Configured maximal temperature [°C] for cooling management
        """
        return self._max

    @property
    def critical(self) -> Optional[float]:
        """
        Configured critical temperature [°C] for cooling management

        If this is reached, overheat flash is set to true
        """
        return self._critical

    @property
    def overheat(self) -> bool:
        """
        Overheat state

        True if overheated, false otherwise
        """
        return self._overheat

    def _on_value_change(self, value: float):
        if value is not None and (
            self._last_logged_temp is None or abs(self._last_logged_temp - value) > self.VALUE_LOGGING_THRESHOLD_DEG_C
        ):
            self._logger.info("%f°C", value)
            self._last_logged_temp = value

        if self._critical is not None:
            self._check_overheat(value)

    def _check_overheat(self, value: float):
        old = self._overheat
        if value is None or value > self._critical:
            self._overheat = True
        if value is not None and value < self._critical - self._hysteresis:
            self._overheat = False
        if self._overheat != old:
            self.overheat_changed.emit(self._overheat)
            if self._overheat:
                self._logger.error("Overheat detected")
            else:
                self._logger.info("Normal temperature")
