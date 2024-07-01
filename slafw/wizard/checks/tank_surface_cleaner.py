# This file is part of the SLA firmware
# Copyright (C) 2020-2024 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from asyncio import sleep
from time import time
from enum import Enum, unique

from slafw.configs.unit import Nm
from slafw.hardware.profiles import SingleProfile
from slafw.hardware.tower import MovingProfilesTower
from slafw.wizard.data_package import WizardDataPackage
from slafw.wizard.actions import UserActionBroker
from slafw.wizard.checks.base import WizardCheckType, DangerousCheck, Check
from slafw.wizard.setup import Configuration, Resource
from slafw.errors.errors import CleaningAdaptorMissing, NotMechanicallyCalibrated

@unique
class GentlyUpProfile(Enum):
    """Gives meaning to the value config.tankCleaningGentlyUpProfile,
    which should be restricted to the prepared(here) selection of
    available profiles for "GentlyUp" operation.
    """

    SPEED0 = 0  # moveSlow (moveSlow)
    SPEED1 = 1  # layer2 (superSlow)
    SPEED2 = 2  # homingSlow
    SPEED3 = 3  # resinSensor (resinSensor)

    def map_to_tower_profile(self, profiles: MovingProfilesTower) -> SingleProfile:
        """Transform the value passed from the frontend via configuration into a name of an actual tower profile"""
        if self == GentlyUpProfile.SPEED1:
            return profiles.layer2
        if self == GentlyUpProfile.SPEED2:
            return profiles.homingSlow
        if self == GentlyUpProfile.SPEED3:
            return profiles.resinSensor
        return profiles.moveSlow    # default and SPEED0


class Calibrated(Check):
    """ Check printer is calibrated """

    def __init__(self, package: WizardDataPackage):
        super().__init__(WizardCheckType.CALIBRATION, Configuration(None, None), [])
        self.calibrated = package.hw.config.calibrated

    async def async_task_run(self, actions: UserActionBroker):
        if not self.calibrated:
            raise NotMechanicallyCalibrated()


class HomeTower(DangerousCheck):
    """ Home tower and request the user to attach the cleaning adaptor to the platform """

    def __init__(self, package: WizardDataPackage):
        super().__init__(package, WizardCheckType.TOWER_HOME, Configuration(None, None), [Resource.TOWER])

    async def async_task_run(self, actions: UserActionBroker):
        await self._package.hw.tower.sync_ensure_async()


class HomeTowerFinish(DangerousCheck):
    """ Home tower at the end of wizard """

    def __init__(self, package: WizardDataPackage):
        super().__init__(package, WizardCheckType.TOWER_HOME_FINISH, Configuration(None, None), [Resource.TOWER])

    async def async_task_run(self, actions: UserActionBroker):
        await self._package.hw.tower.sync_ensure_async(retries=3)


class TiltHome(DangerousCheck):
    """ Home the platform (to the top) """

    def __init__(self, package: WizardDataPackage):
        super().__init__(
            package, WizardCheckType.TILT_HOME, Configuration(None, None), [Resource.TILT, Resource.TOWER_DOWN]
        )

    async def async_task_run(self, actions: UserActionBroker):
        await self._package.hw.tilt.sync_ensure_async()


class TiltUp(DangerousCheck):
    def __init__(self, package: WizardDataPackage):
        super().__init__(
            package, WizardCheckType.TILT_LEVEL, Configuration(None, None), [Resource.TILT, Resource.TOWER_DOWN]
        )
        self._package = package

    async def async_task_run(self, actions: UserActionBroker):
        tilt = self._package.hw.tilt
        tilt.actual_profile = tilt.profiles.layer1750  # use profile with higher current
        await tilt.move_ensure_async(tilt.config_height_position)


class TowerSafeDistance(DangerousCheck):
    """ Move the platform to save distance from the tank """

    def __init__(self, package: WizardDataPackage):
        super().__init__(package, WizardCheckType.TOWER_SAFE_DISTANCE, Configuration(None, None), [Resource.TOWER])

    async def async_task_run(self, actions: UserActionBroker):
        tower = self._package.hw.tower
        tower.actual_profile = tower.profiles.homingFast
        await tower.move_ensure_async(tower.resin_start_pos_nm)


class TouchDown(DangerousCheck):
    """ Move slowly down until you hit something """

    def __init__(self, package: WizardDataPackage):
        super().__init__(package, WizardCheckType.TOWER_TOUCHDOWN, Configuration(None, None), [Resource.TOWER])

    async def async_task_run(self, actions: UserActionBroker):
        hw = self._package.hw
        hw.tower.actual_profile = hw.tower.profiles.resinSensor
        # Note: Do not use towerMoveAbsoluteWaitAsync here. It's periodically calling isTowerOnPosition which
        # is causing the printer to try to fix the tower position

        target_position_nm = hw.config.tankCleaningAdaptorHeight_nm - Nm(3_000_000)
        hw.tower.move(target_position_nm)
        await hw.tower.wait_to_stop_async()
        if target_position_nm == hw.tower.position:
            # Did you forget to put a cleaning adapter pin on corner of the platform?
            hw.tower.actual_profile = hw.tower.profiles.homingFast
            await hw.tower.move_ensure_async(hw.config.tower_height_nm)
            hw.motors_release()
            # Error: The cleaning adaptor is not present, the platform moved to the exposure display without hitting it.
            raise CleaningAdaptorMissing()
        self._logger.info("TouchDown did detect an obstacle - cleaningAdaptor.?")

        self._logger.info("Moving up to the configured height(%d nm)...",
                hw.config.tankCleaningMinDistance_nm)
        lifted_position = hw.tower.position + hw.config.tankCleaningMinDistance_nm
        hw.tower.move(lifted_position)
        await hw.tower.wait_to_stop_async()
        if lifted_position == hw.tower.position:
            self._logger.info("Garbage collector successfully lifted to the initial position.")
        else:
            self._logger.warning("Garbage collector failed to be lifted to the initial position(should be %d, is %d). "
                    "Continuing anyway.", lifted_position, hw.tower.position)


class ExposeDebris(DangerousCheck):
    def __init__(self, package: WizardDataPackage):
        super().__init__(
            package, WizardCheckType.EXPOSING_DEBRIS, Configuration(None, None),
            [Resource.UV, Resource.FANS, Resource.TOWER_DOWN, Resource.TILT]
        )

    async def async_task_run(self, actions: UserActionBroker):
        hw = self._package.hw
        try:  # Handle the possible interruption
            # Exposure display turn "white"
            self._package.exposure_image.open_screen()
            hw.start_fans()
            hw.uv_led.on()
            start_time = time()
            finish_time = time() + hw.config.tankCleaningExposureTime
            while time() < finish_time:
                self.progress = 1 - (finish_time - time()) / (finish_time - start_time)
                await sleep(0.25)
        finally:
            # Return the display to black
            self._package.exposure_image.blank_screen()
            hw.uv_led.off()
            hw.stop_fans()


class GentlyUp(Check):
    """ Move slowly up until you hit something """

    def __init__(self, package: WizardDataPackage):
        super().__init__(WizardCheckType.TOWER_GENTLY_UP, Configuration(None, None), [Resource.TILT, Resource.TOWER])
        self._package = package

    async def async_task_run(self, actions: UserActionBroker):
        up_profile = GentlyUpProfile(self._package.hw.config.tankCleaningGentlyUpProfile)
        tower_profile = up_profile.map_to_tower_profile(self._package.hw.tower.profiles)
        self._logger.info("GentlyUp with %s -> %s", up_profile.name, tower_profile.idx)
        self._package.hw.tower.actual_profile = tower_profile

        tilt = self._package.hw.tilt
        tilt.actual_profile = tilt.profiles.layer1750  # use profile with higher current
        tilt.move(tilt.home_position)
        await tilt.wait_to_stop_async()

        # TODO: constant in code !!!
        target_position = Nm(50_000_000)
        for _ in range(3):
            self._package.hw.tower.move(target_position)
            await self._package.hw.tower.wait_to_stop_async()
            if abs(target_position - self._package.hw.tower.position) < Nm(10):
                break
