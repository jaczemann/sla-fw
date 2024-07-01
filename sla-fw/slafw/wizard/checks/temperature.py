# This file is part of the SLA firmware
# Copyright (C) 2020-2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from dataclasses import dataclass, asdict
from threading import Thread
from time import sleep
from typing import Dict, Any, Optional

from slafw.api.devices import HardwareDeviceId
from slafw.errors.errors import A64Overheat, TempSensorNotInRange
from slafw.functions.system import shut_down
from slafw.wizard.data_package import WizardDataPackage
from slafw.wizard.actions import UserActionBroker
from slafw.wizard.checks.base import WizardCheckType, Check
from slafw.wizard.setup import Configuration


@dataclass
class CheckData:
    # UV LED temperature at the beginning of test (should be close to ambient)
    wizardTempUvInit: float
    # ambient sensor temperature
    wizardTempAmbient: float
    # A64 temperature
    wizardTempA64: float


class TemperatureTest(Check):
    def __init__(self, package: WizardDataPackage):
        super().__init__(WizardCheckType.TEMPERATURE, Configuration(None, None), [])
        self._hw = package.hw
        self._check_data: Optional[CheckData] = None

    async def async_task_run(self, actions: UserActionBroker):
        self._logger.debug("Checking temperatures")

        # A64 overheat check
        self._logger.info("Checking A64 for overheating")
        if self._hw.cpu_temp.overheat:
            Thread(target=self._overheat, daemon=True).start()
            raise A64Overheat(self._hw.cpu_temp.value)

        # Checking MC temperatures
        self._logger.info("Checking MC temperatures")
        uv = self._hw.uv_led_temp
        if not uv.min < uv.value < uv.critical:
            raise TempSensorNotInRange(HardwareDeviceId.UV_LED_TEMP.value, uv.value, uv.min, uv.max)

        ambient = self._hw.ambient_temp
        if not ambient.min < ambient.value < ambient.max:
            raise TempSensorNotInRange(HardwareDeviceId.AMBIENT_TEMP.value, ambient.value, ambient.min, ambient.max)

        self._check_data = CheckData(uv.value, ambient.value, self._hw.cpu_temp.value)

    def _overheat(self):
        for _ in range(10):
            self._hw.beepAlarm(3)
            sleep(1)
        shut_down(self._hw)

    def get_result_data(self) -> Dict[str, Any]:
        return asdict(self._check_data)
