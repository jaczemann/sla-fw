# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from asyncio import sleep
from pathlib import Path
from typing import Optional

from slafw.hardware.temp_sensor import TempSensor


class A64CPUTempSensor(TempSensor):
    CPU_TEMP_PATH = Path("/sys/devices/virtual/thermal/thermal_zone0/temp")
    A64_CPU_TEMP_LIMIT = 80.0  # maximal temperature of A64 is 125 C according to datasheet
    UPDATE_INTERVAL_S = 3

    def __init__(self):
        super().__init__("CPU", critical=self.A64_CPU_TEMP_LIMIT)
        self._value = self._read_value()

    @property
    def value(self) -> float:
        return self._value

    def _read_value(self) -> Optional[float]:
        try:
            with self.CPU_TEMP_PATH.open("r", encoding="utf-8") as f:
                return round((int(f.read()) / 1000.0), 1)
        except ValueError:
            return None

    async def run(self):
        while True:
            value = self._read_value()
            if self._value != value:
                self._value = value
                self.value_changed.emit(value)
            await sleep(self.UPDATE_INTERVAL_S)
