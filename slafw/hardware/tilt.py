# This file is part of the SLA firmware
# Copyright (C) 2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio
from abc import abstractmethod

from slafw.configs.unit import Ustep
from slafw.errors.errors import TiltMoveFailed, TiltHomeFailed
from slafw.hardware.axis import Axis
from slafw.hardware.profiles import SingleProfile, ProfileSet


class MovingProfilesTilt(ProfileSet):
    name = "tilt moving profiles"

    @property
    @abstractmethod
    def homingFast(self) -> SingleProfile:
        pass

    @property
    @abstractmethod
    def homingSlow(self) -> SingleProfile:
        pass

    @property
    @abstractmethod
    def move120(self) -> SingleProfile:
        """
        Former moveSlow for SL1
        """

    @property
    @abstractmethod
    def layer200(self) -> SingleProfile:
        """
        New profile used for printing. Max steprate 200 usteps/s
        """

    @property
    @abstractmethod
    def move300(self) -> SingleProfile:
        """
        Former moveSlow for SL1S/M1
        """

    @property
    @abstractmethod
    def layer400(self) -> SingleProfile:
        """
        Former layerRelease for both SL1 and SL1S/M1
        Max steprate 400 usteps/s
        """

    @property
    @abstractmethod
    def layer600(self) -> SingleProfile:
        """
        Former superSlow for SL1
        Max steprate 600 usteps/s
        """

    @property
    @abstractmethod
    def layer800(self) -> SingleProfile:
        """
        Former superSlow for both SL1S/M1
        Max steprate 800 usteps/s
        """

    @property
    @abstractmethod
    def layer1000(self) -> SingleProfile:
        """
        New profile used for printing. Max steprate 1000 usteps/s
        """

    @property
    @abstractmethod
    def layer1250(self) -> SingleProfile:
        """
        New profile used for printing. Max steprate 1250 usteps/s
        """

    @property
    @abstractmethod
    def layer1500(self) -> SingleProfile:
        """
        Former layerMoveSlow for SL1
        Max steprate 1500 usteps/s
        """

    @property
    @abstractmethod
    def layer1750(self) -> SingleProfile:
        """
        Former layerMoveFast for SL1
        Former layerMoveSlow and layerMoveFast for SL1S/M1
        Max steprate 1750 usteps/s
        """

    @property
    @abstractmethod
    def layer2000(self) -> SingleProfile:
        """
        New profile used for printing. Max steprate 2000 usteps/s
        """

    @property
    @abstractmethod
    def layer2250(self) -> SingleProfile:
        """
        New profile used for printing. Max steprate 2250 usteps/s
        """

    @property
    @abstractmethod
    def move5120(self) -> SingleProfile:
        """
        Former moveFast for SL1
        """

    @property
    @abstractmethod
    def move8000(self) -> SingleProfile:
        """
        Former moveFast for SL1S/M1
        """


class Tilt(Axis):

    @property
    def name(self) -> str:
        return "tilt"

    @property
    def sensitivity(self) -> int:
        return self._config.tiltSensitivity

    @property
    def home_position(self) -> Ustep:
        return Ustep(0)

    @property
    def config_height_position(self) -> Ustep:
        return self._config.tiltHeight

    @property
    def minimal_position(self) -> Ustep:
        return self.home_position

    def layer_up_wait(self, layer_profile: SingleProfile, tilt_height: Ustep=Ustep(0)) -> None:
        asyncio.run(self.layer_up_wait_async(layer_profile, tilt_height))

    @abstractmethod
    async def layer_up_wait_async(self, layer_profile: SingleProfile, tilt_height: Ustep=Ustep(0)) -> None:
        """tilt up during the print"""

    def layer_down_wait(self, layer_profile: SingleProfile) -> None:
        asyncio.run(self.layer_down_wait_async(layer_profile))

    @abstractmethod
    async def layer_down_wait_async(self, layer_profile: SingleProfile) -> None:
        """tilt up during the print"""

    def stir_resin(self, layer_profile: SingleProfile) -> None:
        asyncio.run(self.stir_resin_async(layer_profile))

    @abstractmethod
    async def stir_resin_async(self, layer_profile: SingleProfile) -> None:
        """stiring moves of tilt."""

    def _move_api_min(self) -> None:
        self.move(self.home_position)

    def _move_api_max(self) -> None:
        self.move(self._config.tiltMax)

    @staticmethod
    def _raise_move_failed():
        raise TiltMoveFailed()

    @staticmethod
    def _raise_home_failed():
        raise TiltHomeFailed()

    @property
    @abstractmethod
    def profiles(self) -> MovingProfilesTilt:
        """all tilt profiles"""
