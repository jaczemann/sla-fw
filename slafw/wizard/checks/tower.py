# This file is part of the SLA firmware
# Copyright (C) 2020-2024 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from asyncio import gather
from typing import Dict, Any

from slafw.configs.unit import Nm
from slafw.errors.errors import TowerBelowSurface, TowerAxisCheckFailed, TowerHomeFailed, TowerEndstopNotReached
from slafw.wizard.data_package import WizardDataPackage
from slafw.wizard.actions import UserActionBroker
from slafw.wizard.checks.base import WizardCheckType, DangerousCheck
from slafw.wizard.setup import Configuration, Resource, TankSetup, PlatformSetup


class TowerHomeTest(DangerousCheck):
    def __init__(self, package: WizardDataPackage):
        super().__init__(
            package, WizardCheckType.TOWER_HOME, Configuration(None, None), [Resource.TOWER, Resource.TOWER_DOWN],
        )

    async def async_task_run(self, actions: UserActionBroker):
        hw = self._package.hw
        for sensitivity in range(4):
            sensitivity_failed = False
            for _ in range(3):
                try:
                    await hw.tower.sync_ensure_async(retries=0)
                except (TowerHomeFailed, TowerEndstopNotReached) as e:
                    sensitivity_failed = True
                    self._logger.exception(e)
                    if sensitivity == 3:
                        raise e
                    hw.tower.set_stepper_sensitivity(sensitivity)
                    hw.tower.profiles.apply_all()
                    self._package.config_writers.hw_config.towerSensitivity = sensitivity   # FIXME this should only be done upon success
                    break
            if sensitivity_failed is False:
                break

    def get_result_data(self) -> Dict[str, Any]:
        return {
            # measured fake resin volume in wizard (without resin with rotated platform)
            "towerSensitivity": self._package.config_writers.hw_config.towerSensitivity
        }


class TowerRangeTest(DangerousCheck):
    def __init__(self, package: WizardDataPackage):
        super().__init__(
            package, WizardCheckType.TOWER_RANGE, Configuration(None, None), [Resource.TOWER, Resource.TOWER_DOWN],
        )

    async def async_task_run(self, actions: UserActionBroker):
        hw = self._package.hw
        await self.wait_cover_closed()
        await gather(hw.tower.verify_async(), hw.tilt.verify_async())
        hw.tower.position = hw.tower.end_nm

        hw.tower.actual_profile = hw.tower.profiles.homingFast
        await hw.tower.move_ensure_async(Nm(0))

        if hw.tower.position == Nm(0):
            # stop 10 mm before end-stop to change sensitive profile
            await hw.tower.move_ensure_async(hw.tower.end_nm - Nm(10_000_000))

            hw.tower.actual_profile = hw.tower.profiles.homingSlow
            hw.tower.move(hw.tower.max_nm)
            await hw.tower.wait_to_stop_async()

        position_nm = hw.tower.position
        # MC moves tower by 1024 steps forward in last step of !twho
        maximum_nm = hw.tower.end_nm + hw.config.tower_microsteps_to_nm(1024 + 127)
        self._logger.info("maximum nm %d", maximum_nm)
        if (
            position_nm < hw.tower.end_nm or position_nm > maximum_nm
        ):  # add tolerance half full-step
            raise TowerAxisCheckFailed(position_nm)


class TowerAlignTest(DangerousCheck):
    def __init__(self, package: WizardDataPackage):
        super().__init__(
            package,
            WizardCheckType.TOWER_CALIBRATION,
            Configuration(TankSetup.PRINT, PlatformSetup.PRINT),
            [Resource.TOWER, Resource.TOWER_DOWN],
        )

    async def async_task_run(self, actions: UserActionBroker):
        hw = self._package.hw
        await self.wait_cover_closed()
        self._logger.info("Starting platform calibration")
        hw.tilt.actual_profile = hw.tilt.profiles.layer1500 # set higher current
        hw.tower.position = Nm(0)
        hw.tower.actual_profile = hw.tower.profiles.homingFast

        self._logger.info("Moving platform to above position")
        hw.tower.move(hw.tower.above_surface_nm)
        await hw.tower.wait_to_stop_async()

        self._logger.info("tower position above: %d nm", hw.tower.position)
        if hw.tower.position != hw.tower.above_surface_nm:
            self._logger.error(
                "Platform calibration [above] failed %s != %s Nm",
                hw.tower.position,
                hw.tower.above_surface_nm,
            )
            hw.beepAlarm(3)
            await hw.tower.sync_ensure_async()
            raise TowerBelowSurface(hw.tower.position)

        self._logger.info("Moving platform to min position")
        hw.tower.actual_profile = hw.tower.profiles.homingSlow
        hw.tower.move(hw.tower.min_nm)
        await hw.tower.wait_to_stop_async()
        self._logger.info("tower position min: %d nm", hw.tower.position)
        if hw.tower.position <= hw.tower.min_nm:
            self._logger.error(
                "Platform calibration [min] failed %s != %s",
                hw.tower.position,
                hw.tower.min_nm,
            )
            hw.beepAlarm(3)
            await hw.tower.sync_ensure_async()
            raise TowerBelowSurface(hw.tower.position)

        self._logger.debug("Moving tower to calib position x3")
        await hw.tower.move_ensure_async(
            hw.tower.position + hw.tower.calib_pos_nm * 3)

        self._logger.debug("Moving tower to min")
        # do not ensure position here. We expect tower to stop on stallguard
        hw.tower.move(hw.tower.position + hw.tower.min_nm)
        await hw.tower.wait_to_stop_async()

        self._logger.debug("Moving tower to calib position")
        # use less sensitive profile to prevent false stalguard detection
        hw.tower.actual_profile = hw.tower.profiles.homingFast
        # raise exception if the movement fails
        await hw.tower.move_ensure_async(
            hw.tower.position + hw.tower.calib_pos_nm, retries=0)

        tower_position_nm = hw.tower.position
        self._logger.info("tower position: %d nm", tower_position_nm)
        self._package.config_writers.hw_config.tower_height_nm = -tower_position_nm

        hw.tower.actual_profile = hw.tower.profiles.homingFast
        # TODO: Allow to repeat align step on exception

    def get_result_data(self) -> Dict[str, Any]:
        return {
            "tower_height_nm": int(self._package.config_writers.hw_config.tower_height_nm),
        }
