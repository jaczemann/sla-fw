# This file is part of the SLA firmware
# Copyright (C) 2020-2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from asyncio import sleep
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, List

from slafw import defines
from slafw.api.devices import HardwareDeviceId
from slafw.errors.errors import FanRPMOutOfTestRange, UVLEDHeatsinkFailed
from slafw.wizard.data_package import WizardDataPackage
from slafw.wizard.actions import UserActionBroker
from slafw.wizard.checks.base import WizardCheckType, DangerousCheck
from slafw.wizard.setup import Configuration, Resource


@dataclass
class CheckData:
    # fans RPM when using default PWM
    wizardFanRpm: list
    # UV LED temperature at the beginning of test (should be close to ambient)
    wizardTempUvWarm: float


class UVFansTest(DangerousCheck):
    def __init__(self, package: WizardDataPackage):
        super().__init__(
            package,
            WizardCheckType.UV_FANS,
            Configuration(None, None),
            [Resource.FANS, Resource.UV],
        )
        self._check_data: Optional[CheckData] = None

    async def async_task_run(self, actions: UserActionBroker):
        # pylint: disable=too-many-branches
        # pylint: disable=too-many-locals
        hw = self._package.hw
        await self.wait_cover_closed()

        fan_diff = 200
        hw.start_fans()
        hw.uv_led_fan.auto_control = False
        for fan in hw.fans.values():
            fan.target_rpm = fan.default_rpm
        hw.uv_led.on()
        rpm: List[List[int]] = [[], [], []]
        fans_wait_time = defines.fanWizardStabilizeTime + defines.fanStartStopTime

        hw.uv_led.pwm = hw.uv_led.max_pwm

        uv_temp = hw.uv_led_temp.value
        try:  # check may be interrupted by another check or canceled
            for countdown in range(hw.config.uvWarmUpTime, 0, -1):
                self.progress = 1 - countdown / hw.config.uvWarmUpTime

                # Store fan statistics
                if fans_wait_time < hw.config.uvWarmUpTime - countdown:
                    for i, fan in hw.fans.items():
                        rpm[i].append(fan.rpm)

                # Report imminent failure
                uv_temp = hw.uv_led_temp.value
                if uv_temp > defines.maxUVTemp:
                    raise UVLEDHeatsinkFailed(uv_temp)
                if any([fan.error for fan in hw.fans.values()]):
                    self._logger.error("Skipping UV Fan check due to fan failure")
                    break

                await sleep(1)
        finally:
            hw.uv_led.off()
            hw.uv_led_fan.auto_control = True
            hw.stop_fans()

        # evaluate fans data
        avg_rpms = []

        for i, fan in hw.fans.items():  # iterate over fans
            rpms = rpm[i] if len(rpm[i]) else [0]
            avg_rpm = sum(rpms) / len(rpms)
            lower_bound_rpm = fan.target_rpm - fan_diff
            upper_bound_rpm = fan.target_rpm + fan_diff
            if not lower_bound_rpm <= avg_rpm <= upper_bound_rpm or fan.error:
                self._logger.error("Fan %s: raw RPM: %s, error: %s, samples: %s", fan.name, rpm, fan.error, len(rpms))

                if fan == hw.uv_led_fan:
                    hw_id = HardwareDeviceId.UV_LED_FAN
                elif fan == hw.blower_fan:
                    hw_id = HardwareDeviceId.BLOWER_FAN
                elif fan == hw.rear_fan:
                    hw_id = HardwareDeviceId.REAR_FAN
                else:
                    raise ValueError("Unknown failing fan")

                raise FanRPMOutOfTestRange(
                    hw_id.value,
                    min(rpms),
                    max(rpms),
                    round(avg_rpm),
                    lower_bound_rpm,
                    upper_bound_rpm,
                    int(fan.error),
                )

            avg_rpms.append(avg_rpm)

        # evaluate UV LED data
        if uv_temp > defines.maxUVTemp:
            raise UVLEDHeatsinkFailed(uv_temp)

        self._check_data = CheckData(avg_rpms, uv_temp)

    def get_result_data(self) -> Dict[str, Any]:
        return asdict(self._check_data)
