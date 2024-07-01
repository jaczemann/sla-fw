# This file is part of the SLA firmware
# Copyright (C) 2021-2022 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio
import logging
import re
from abc import ABC, abstractmethod
from enum import unique, Enum
from typing import List, Dict, Any

from PySignal import Signal

from slafw.configs.hw import HwConfig
from slafw.configs.unit import Unit, Nm
from slafw.errors.errors import MotionControllerException
from slafw.hardware.power_led import PowerLed
from slafw.hardware.power_led_action import WarningAction
from slafw.hardware.profiles import SingleProfile, ProfileSet


def parse_axis(text: str, axis: str) -> int:
    try:
        mm, dec = re.search(fr"(?<={axis}:)([0-9]*)\.([0-9]*)", text).groups()
        nm = int(mm) * 1000 * 1000
        for i, c in enumerate(dec):
            if i <= 5:
                nm += int(c) * 10 ** (5 - i)
    except Exception as exception:
        raise ValueError from exception

    return nm


def format_axis(position_nm: int) -> str:
    return f"{position_nm // 1000000}.{position_nm % 1000000}"


@unique
class HomingStatus(Enum):
    """
    Use similar reporting from klipper
    """
    BLOCKED_AXIS = -3
    ENDSTOP_NOT_REACHED = -2
    UNKNOWN = -1    # homing was not initiated yet
    SYNCED = 0  # axis was successfully homed.
    STARTED = 1
    GO_COARSE = 2
    GO_BACK_COARSE = 3
    GO_FINE = 4
    GO_BACK_FINE = 5
    TILT_GO_FINE = 6  # FIXME: use unified IDs for tilt and tower in mc-fw
    TILT_GO_BACK_FINE = 7  # FIXME: use unified IDs for tilt and tower in mc-fw


class Axis(ABC):
    # pylint: disable=too-many-public-methods
    # pylint: disable=too-many-instance-attributes
    _target_position: Unit = Unit(0)
    _last_position: Unit = Unit(0)  # used by move_api
    _sensitivity: Dict[str, List[List[int]]]
    _wait_to_stop_delay: float = 0.1

    def __init__(self, config: HwConfig, power_led: PowerLed):
        super().__init__()
        self._logger = logging.getLogger(self.__class__.__name__)
        self.movement_ended = Signal()
        self._config = config
        self._power_led = power_led

    @property
    def name(self) -> str:
        """return axis name"""

    @property
    @abstractmethod
    def home_position(self) -> Unit:
        """
        returns value with home position
        Tower - top position (config.tower_height_nm)
        Tilt - bottom position (0)
        """

    @property
    @abstractmethod
    def config_height_position(self) -> Unit:
        """
        returns value with calibrated height position
        Tower - top position (config.tower_height_nm)
        Tilt - level position (config.tiltHeight)
        """

    @property
    @abstractmethod
    def minimal_position(self) -> Unit:
        """
        returns value with minimlal position (0)
        """

    @property
    @abstractmethod
    def position(self) -> Unit:
        """get current position of the axis"""

    @position.setter
    @abstractmethod
    def position(self, position: Unit) -> None:
        """set current position of the axis"""

    @property
    def on_target_position(self) -> bool:
        """
        Returns True if axis position equals its target position. Otherwise return False.
        This property does not care if axis is already moving or stopped.

        """
        if self.moving:
            return False
        if self.position != self._target_position:
            self._logger.warning(
                "Not on required position! Actual position: %d, Target "
                "position: %d, unit: %s",
                self.position,
                self._target_position,
                type(self._target_position)
            )
            return False
        return True

    async def ensure_position_async(self, retries: int = 1) -> None:
        """
        Waits for move to finish and checks the position.
        If current position is not target, retries X times to home and
        returns to target position

        :param: number os subsequent rehoming
        :return: None, otherwise raises Exception
        """
        await self.wait_to_stop_async()

        while self._target_position != self.position:
            if retries:
                retries -= 1
                self._logger.warning(
                    "Not on required position! Sync forced. Actual position: %d, Target position: %d, unit: %s",
                    self.position,
                    self._target_position,
                    type(self._target_position)
                )
                profile_backup = self.actual_profile
                await self.sync_ensure_async()
                self.actual_profile = profile_backup
                self.move(self._target_position)
                await self.wait_to_stop_async()
            else:
                self._logger.error("Position max tries reached!")
                self._raise_move_failed()

    @staticmethod
    @abstractmethod
    def _raise_move_failed():
        """Immediately raises axis move exception"""

    @property
    @abstractmethod
    def moving(self) -> bool:
        """determine if axis is moving at the moment"""

    def wait_to_stop(self) -> None:
        """blocking method to wait for axis to stop"""
        asyncio.run(self.wait_to_stop_async())

    async def wait_to_stop_async(self) -> None:
        """blocking method to wait for axis to stop"""
        while self.moving:
            # WARNING: do not change this 0.1 sleep, since time calculations will be off.
            await asyncio.sleep(self._wait_to_stop_delay)

    @abstractmethod
    def move(self, position: Unit) -> None:
        """initiate movement of the axis"""

    def move_ensure(self, position: Unit, retries=1) -> None:
        """initiate blocking movement of the axis"""
        asyncio.run(self.move_ensure_async(position, retries))

    async def move_ensure_async(self, position: Unit, retries=1) \
            -> None:
        """initiate blocking movement of the axis"""
        self.move(position)
        await self.ensure_position_async(retries)

    def move_api(self, speed: int, fullstep: bool = False) -> bool:
        """
        Start / stop tilt movement

        TODO: This should be checked by heartbeat or the command should have limited ttl

        :param: Movement speed

           :-2: Fast down
           :-1: Slow down
           :0: Stop
           :1: Slow up
           :2: Fast up
        :return: True on success, False otherwise
        """
        # do not change the profile while temporary profile is selected (profile testing in admin)
        if not self.moving and speed != 0 and self.actual_profile.idx != -1:
            self.actual_profile = self._move_api_get_profile(speed)

        if speed != 0:
            self._last_position = self.position
            if speed < 0:
                self._move_api_min()
            else:
                self._move_api_max()
            return True

        self.stop()
        if fullstep:
            self._logger.info("fullstep last pos %d", self._last_position)
            if self._last_position < self.position:
                self.go_to_fullstep(go_up=True)
            elif self._last_position > self.position:
                self.go_to_fullstep(go_up=False)
        self.movement_ended.emit()
        return True

    @abstractmethod
    def _move_api_min(self) -> None:
        """nonblocking move to the lowest position"""

    @abstractmethod
    def _move_api_max(self) -> None:
        """nonblocking move to the highest position"""

    @abstractmethod
    def _move_api_get_profile(self, speed: int) -> SingleProfile:
        """returns slow/fast profile for high level movement"""

    @abstractmethod
    def stop(self) -> None:
        """stop movement of the axis (do not release)"""

    @abstractmethod
    def release(self) -> None:
        """release stepper motor (disable)"""

    @abstractmethod
    def go_to_fullstep(self, go_up: bool):
        """move axis to the fullstep (stable position) in given direction"""

    @abstractmethod
    def sync(self) -> None:
        """start axis homing"""

    @property
    def synced(self) -> bool:
        """basic check if axis is synchronized (homing has succesfully finished)"""
        return self.homing_status == HomingStatus.SYNCED

    @property
    @abstractmethod
    def homing_status(self) -> HomingStatus:
        """get actual state of axis homing"""

    def sync_ensure(self, retries: int = 2) -> None:
        """blocking method for axis homing. retries = number of additional tries when homing fails"""
        asyncio.run(self.sync_ensure_async(retries=retries))

    async def sync_ensure_async(self, retries: int = 2) -> None:
        """blocking method for axis homing. retries = number of additional tries when homing fails"""
        with WarningAction(self._power_led):
            while True:
                self.sync()
                await self.wait_to_stop_async()
                while True:
                    homing_status = self.homing_status
                    if homing_status.value == HomingStatus.SYNCED.value:
                        self.position = self.home_position
                        return
                    if homing_status.value < HomingStatus.SYNCED.value:
                        self._logger.warning("Homing failed! Status: %s",
                                             homing_status)
                        if retries < 1:
                            self._logger.error("Homing max tries reached!")
                            self._raise_home_failed()
                        retries -= 1
                        break
                    await asyncio.sleep(self._wait_to_stop_delay)

    @staticmethod
    @abstractmethod
    def _raise_home_failed():
        """Immediately raises axis home exception"""

    def home_calibrate_wait(self):
        """test and save axis motor phase for accurate homing"""
        return asyncio.run(self.home_calibrate_wait_async())

    @abstractmethod
    async def home_calibrate_wait_async(self):
        """test and save axis motor phase for accurate homing"""
        homing_status = HomingStatus.STARTED.value
        while homing_status > HomingStatus.SYNCED.value:  # not done and not error
            homing_status = self.homing_status.value
            if homing_status < HomingStatus.SYNCED.value:
                raise MotionControllerException(
                    "Homing calibration failed", None)
            await asyncio.sleep(0.1)

    @abstractmethod
    async def verify_async(self) -> None:
        """
        Checks if axis is synced and at the initial position.
        If not it initiates the movement.
        Tower - top position.
        Tilt - level position.
        """

    @property
    @abstractmethod
    def profiles(self) -> ProfileSet:
        """all axis profiles"""

    @property
    @abstractmethod
    def actual_profile(self) -> SingleProfile:
        """return selected profile"""

    @actual_profile.setter
    @abstractmethod
    def actual_profile(self, profile: SingleProfile):
        """select profile"""

    @abstractmethod
    def apply_profile(self, profile: SingleProfile):
        """update values of currently selected profile in MC"""

    @abstractmethod
    def apply_all_profiles(self) -> None:
        """refresh stepper profiles in MC"""

    @property
    @abstractmethod
    def sensitivity(self) -> int:
        """return config axis sensitivity value"""

    @property
    def sensitivity_dict(self) -> Dict[str, List[List[int]]]:
        """return dict with axis sensitivity values"""
        return self._sensitivity

    @abstractmethod
    def set_stepper_sensitivity(self, sensitivity: int):
        """set the sensitivity of the axis"""

    @staticmethod
    def _check_units(value: Any, unit: Unit) -> None:
        """
        Raises TypeError if the value is not the same Unit as value
        """
        if not isinstance(value, unit):
            raise TypeError(f"Incompatible units {type(value)}, {unit}")

    @abstractmethod
    async def layer_peel_moves_async(self, layer_profile: SingleProfile, position_nm: Nm, last_layer: bool) -> None:
        """do the moves to peel the layer (layer change)"""

    def layer_peel_moves(self, layer_profile: SingleProfile, position_nm: Nm, last_layer: bool) -> None:
        asyncio.run(self.layer_peel_moves_async(layer_profile, position_nm, last_layer))
