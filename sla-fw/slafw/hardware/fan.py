# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
from abc import abstractmethod, ABC
from typing import Optional

from PySignal import Signal

from slafw.hardware.component import HardwareComponent
from slafw.hardware.temp_sensor import TempSensor
from slafw.configs.writer import ConfigWriter


class Fan(HardwareComponent, ABC):
    # pylint: disable = too-many-arguments
    # pylint: disable = too-many-instance-attributes

    AUTO_CONTROL_INTERVAL_S = 30
    VALUE_LOGGING_THRESHOLD_RPM = 500

    def __init__(
        self,
        name: str,
        min_rpm: int,
        max_rpm: int,
        default_rpm: int,
        enabled: bool,
        reference: Optional[TempSensor] = None,
        auto_control: bool = False,
    ):
        super().__init__(name)
        self.rpm_changed = Signal()
        self.error_changed = Signal()
        self._min_rpm = min_rpm
        self._max_rpm = max_rpm
        self._default_rpm = default_rpm
        self._enabled = enabled
        self._reference = reference
        self._auto_control = False
        if auto_control:
            if reference:
                self._auto_control = True
            else:
                raise ValueError("Cannot set auto control, no reference temperature sensor")
        self._last_logged_rpm: Optional[int] = None

        self.rpm_changed.connect(self._on_rpm_changed)
        self.error_changed.connect(self._on_error_changed)

    @abstractmethod
    def save(self, writer: ConfigWriter):
        """
        Store actual settings to writer
        """

    @property
    def running(self) -> bool:
        return self._running

    @running.setter
    def running(self, value: bool):
        if self._enabled:
            self._running = value
        elif value:
            self._logger.info("Fan %s not turned on (disabled)", self.name)
        else:
            self._running = False

    @property
    @abstractmethod
    def _running(self) -> bool:
        """
        Get fan state
        """

    @_running.setter
    @abstractmethod
    def _running(self, value: bool):
        """
        Start/stop the fan
        """

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value
        if not value and self.running:
            self._running = False
            self._logger.info("Fan %s was stopped (disabled)", self.name)

    @property
    @abstractmethod
    def rpm(self) -> int:
        """
        Fan RPM as reported by the fan
        """

    @property
    @abstractmethod
    def error(self) -> bool:
        """
        Fan failed status as reported by the fan
        """

    @property
    @abstractmethod
    def target_rpm(self) -> int:
        """
        Target RPM to be maintained by fan
        """

    @target_rpm.setter
    @abstractmethod
    def target_rpm(self, value: int):
        ...

    @property
    def default_rpm(self) -> int:
        return self._default_rpm

    @default_rpm.setter
    def default_rpm(self, value: int):
        self._default_rpm = self._adapt_rpm(value)
        if not self.auto_control:
            self.target_rpm = self._default_rpm

    @property
    def min_rpm(self) -> int:
        return self._min_rpm

    @property
    def max_rpm(self) -> int:
        return self._max_rpm

    @property
    def has_auto_control(self):
        return bool(self._reference)

    @property
    def auto_control(self):
        return self._auto_control

    @auto_control.setter
    def auto_control(self, value: bool):
        if value and not self._reference:
            raise ValueError("Cannot set auto control, no reference temperature sensor")
        self._auto_control = value
        if not value:
            self.target_rpm = self.default_rpm

    async def run(self):
        await super().run()
        if self._reference:
            await asyncio.create_task(self._fan_rpm_control_task())

    async def _fan_rpm_control_task(self):
        """
        Automatic RPM control based on reference temp sensor value
        """
        self._logger.info("Starting automatic RPM control")
        while True:
            try:
                await asyncio.sleep(self.AUTO_CONTROL_INTERVAL_S)
                await self._fan_rpm_control()
            except Exception:
                self._logger.exception("Fan auto RPM control crashed - running at max RPM")
                self.target_rpm = self.max_rpm
                raise

    async def _fan_rpm_control(self):
        if not self.auto_control:
            self._logger.debug("Automatic RPM control is disabled")
            return

        if not self.running:
            self._logger.debug("Automatic RPM control - fan is not running")
            return

        map_constant = (self.max_rpm - self.min_rpm) / (self._reference.max - self._reference.min)
        rpm = round((self._reference.value - self._reference.min) * map_constant + self.min_rpm)
        rpm = max(min(rpm, self.max_rpm), self.min_rpm)
        self._logger.debug("Fan RPM control setting RPMs: %s", rpm)
        self.target_rpm = rpm

    def _on_rpm_changed(self, rpm: int):
        if rpm is not None and (
            self._last_logged_rpm is None or abs(self._last_logged_rpm - rpm) > self.VALUE_LOGGING_THRESHOLD_RPM
        ):
            self._logger.info("%d RPMs", rpm)
            self._last_logged_rpm = rpm

    def _on_error_changed(self, error: bool):
        if error:
            self._logger.error("Failed")
        else:
            self._logger.info("Recovered")

    def _adapt_rpm(self, value: int) -> int:
        adapted = value
        if value > self.max_rpm:
            adapted = self.max_rpm
        elif value < self.min_rpm:
            adapted = self.min_rpm
        if adapted != value:
            self._logger.warning("Adapting rpm value from %s to %s", value, adapted)
        return adapted
