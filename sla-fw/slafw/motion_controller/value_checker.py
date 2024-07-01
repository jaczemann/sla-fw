# This file is part of the SLA firmware
# Copyright (C) 2020 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio
from asyncio import Event, AbstractEventLoop
from datetime import timedelta
from typing import Callable, Optional

from PySignal import Signal


class UpdateInterval:
    def __init__(self, normal=timedelta(seconds=1), rapid=timedelta(milliseconds=250)):
        self._normal = normal
        self._rapid = rapid

    def get_seconds(self, rapid: bool) -> float:
        if rapid:
            return self._rapid.total_seconds()
        return self._normal.total_seconds()

    @classmethod
    def seconds(cls, seconds: int):
        return UpdateInterval(normal=timedelta(seconds=seconds))


class ControlledDelay:
    def __init__(self):
        self._delay_signal: Optional[Event] = None
        self._loop: Optional[AbstractEventLoop] = None

    async def delay(self, delay_s: float):
        """
        Controlled delay

        This waits for delay_s seconds or until the signal is set. This way the delay can be skipped in case of rapid
        updates being enabled. Another approach would be to make this a simple asyncio.task. Then the delay may be
        skipped by canceling the task. Unfortunately Python < 3.9 cannot distinguish cancel source. Therefore, once
        the code handles the Cancelled exception it cannot be canceled by Printer.exit .
        """
        self._loop = asyncio.get_running_loop()
        self._delay_signal = Event()
        try:
            await asyncio.wait_for(self._delay_signal.wait(), delay_s)
        except asyncio.exceptions.TimeoutError:
            pass

    def cancel(self):
        if self._delay_signal:
            self._loop.call_soon_threadsafe(self._delay_signal.set)


class ValueChecker:
    """
    Utility class for checking values for change
    """

    def __init__(
        self,
        getter: Callable,
        signal: Optional[Signal],
        interval: UpdateInterval = UpdateInterval(),
        pass_value: bool = True,
    ):
        self._getter = getter
        self._event = signal
        self._pass_value = pass_value
        self._last_value = None
        self._interval = interval
        self._rapid_update = False
        self._delay = ControlledDelay()

    def set_rapid_update(self, value: bool) -> None:
        self._rapid_update = value
        self._delay.cancel()

    async def check(self):
        """
        This periodically checks the value

        Run this as an asyncio task to maintain a periodic check of the values.
        """
        while True:
            new_value = self._getter()
            if self._last_value is None or self._last_value != new_value:
                self._last_value = new_value
                self.emit(new_value)
            await self._delay.delay(self._interval.get_seconds(self._rapid_update))

    def emit(self, value):
        if self._event is not None:
            if self._pass_value:
                self._event.emit(value)
            else:
                self._event.emit()
