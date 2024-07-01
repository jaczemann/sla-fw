# This file is part of the SLA firmware
# Copyright (C) 2020-2024 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio
from abc import ABC
from typing import Optional, Dict, Any

from slafw import defines
from slafw.configs.unit import Ustep
from slafw.errors.errors import (
    TiltHomeCheckFailed,
    TiltEndstopNotReached,
    TiltAxisCheckFailed,
    InvalidTiltAlignPosition,
    PrinterException,
)
from slafw import test_runtime
from slafw.states.wizard import WizardState
from slafw.wizard.data_package import WizardDataPackage
from slafw.wizard.actions import UserActionBroker, PushState
from slafw.wizard.checks.base import WizardCheckType, DangerousCheck, Check
from slafw.wizard.setup import Configuration, Resource, TankSetup


class TiltHomeTest(DangerousCheck, ABC):
    def __init__(self, package: WizardDataPackage):
        super().__init__(
            package, WizardCheckType.TILT_HOME, Configuration(None, None), [Resource.TILT, Resource.TOWER_DOWN],
        )

    async def async_task_run(self, actions: UserActionBroker):
        hw = self._package.hw
        home_status = hw.tilt.homing_status
        for _ in range(3):
            await hw.tilt.sync_ensure_async()
            home_status = hw.tilt.homing_status
            if home_status == -2:
                raise TiltEndstopNotReached()

            if home_status == 0:
                await hw.tilt.home_calibrate_wait_async()
                break

        if home_status == -3:
            raise TiltHomeCheckFailed()


class TiltLevelTest(DangerousCheck):
    def __init__(self, package: WizardDataPackage):
        super().__init__(
            package, WizardCheckType.TILT_LEVEL, Configuration(None, None), [Resource.TILT, Resource.TOWER_DOWN]
        )

    async def async_task_run(self, actions: UserActionBroker):
        hw = self._package.hw
        # This just homes tilt
        # TODO: We should have such a method in Hardware
        hw.tilt.actual_profile = hw.tilt.profiles.homingFast
        hw.tilt.sync()
        home_status = hw.tilt.homing_status.value
        while home_status != 0:
            if home_status == -2:
                raise TiltEndstopNotReached()
            if home_status == -3:
                raise TiltHomeCheckFailed()
            if home_status < 0:
                raise PrinterException("Unknown printer home error")
            await asyncio.sleep(0.25)
            home_status = hw.tilt.homing_status.value
        hw.tilt.position = Ustep(0)

        # Set tilt to leveled position
        hw.tilt.actual_profile = hw.tilt.profiles.move8000
        await hw.tilt.move_ensure_async(hw.config.tiltHeight)


class TiltRangeTest(DangerousCheck):
    def __init__(self, package: WizardDataPackage):
        super().__init__(
            package, WizardCheckType.TILT_RANGE, Configuration(None, None), [Resource.TILT, Resource.TOWER_DOWN],
        )

    async def async_task_run(self, actions: UserActionBroker):
        hw = self._package.hw
        hw.tilt.actual_profile = hw.tilt.profiles.move8000
        hw.tilt.move(hw.config.tiltMax)
        await hw.tilt.wait_to_stop_async()
        self.progress = 0.25

        hw.tilt.move(Ustep(512))  # go down fast before endstop
        await hw.tilt.wait_to_stop_async()
        self.progress = 0.5

        # finish measurement with slow profile (more accurate)
        hw.tilt.actual_profile = hw.tilt.profiles.homingSlow
        hw.tilt.move(hw.config.tiltMin)
        await hw.tilt.wait_to_stop_async()
        self.progress = 0.75

        # TODO make MC homing more accurate
        if (
            hw.tilt.position < Ustep(-defines.tiltHomingTolerance)
            or hw.tilt.position > Ustep(defines.tiltHomingTolerance)
        ) and not test_runtime.testing:
            raise TiltAxisCheckFailed(hw.tilt.position)
        hw.tilt.actual_profile = hw.tilt.profiles.move8000
        hw.tilt.move(hw.config.tiltHeight)
        await hw.tilt.wait_to_stop_async()


class TiltCalibrationStartTest(DangerousCheck):
    def __init__(self, package: WizardDataPackage):
        super().__init__(
            package,
            WizardCheckType.TILT_CALIBRATION_START,
            Configuration(None, None),
            [Resource.TILT, Resource.TOWER_DOWN],
        )

    async def async_task_run(self, actions: UserActionBroker):
        hw = self._package.hw
        hw.tilt.actual_profile = hw.tilt.profiles.homingFast
        hw.tilt.move(Ustep(defines.tiltCalibrationStart))
        await hw.tilt.wait_to_stop_async()


class TiltAlignTest(Check):
    def __init__(self, package: WizardDataPackage):
        super().__init__(
            WizardCheckType.TILT_CALIBRATION,
            Configuration(TankSetup.REMOVED, None),
            [Resource.TILT, Resource.TOWER_DOWN],
        )
        self._package = package
        self.tilt_aligned_event: Optional[asyncio.Event] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def async_task_run(self, actions: UserActionBroker):
        self.tilt_aligned_event = asyncio.Event()
        self._loop = asyncio.get_running_loop()
        actions.tilt_aligned.register_callback(self.tilt_aligned)
        actions.tilt_move.register_callback(self.tilt_move)

        level_tilt_state = PushState(WizardState.LEVEL_TILT)
        actions.push_state(level_tilt_state)
        await self.tilt_aligned_event.wait()
        actions.drop_state(level_tilt_state)

    def tilt_aligned(self):
        position = self._package.hw.tilt.position
        if position is None:
            self._package.hw.beepAlarm(3)
            raise InvalidTiltAlignPosition(position)
        self._package.config_writers.hw_config.tiltHeight = position
        self._loop.call_soon_threadsafe(self.tilt_aligned_event.set)

    def tilt_move(self, direction: int):
        self._logger.debug("Tilt move direction: %s", direction)
        self._package.hw.tilt.move_api(direction, fullstep=True)

    def get_result_data(self) -> Dict[str, Any]:
        return {"tiltHeight": int(self._package.config_writers.hw_config.tiltHeight)}
