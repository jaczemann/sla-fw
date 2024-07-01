# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from abc import abstractmethod

from slafw.configs.unit import Nm
from slafw.errors.errors import TowerMoveFailed, TowerHomeFailed
from slafw.hardware.axis import Axis
from slafw.hardware.profiles import SingleProfile, ProfileSet


class MovingProfilesTower(ProfileSet):
    name = "tower moving profiles"

    @property
    @abstractmethod
    def homingFast(self) -> SingleProfile:
        """
        Profile with tuned stallGuard. Used for homing and printer0 move_tower.
        """

    @property
    @abstractmethod
    def homingSlow(self) -> SingleProfile:
        """
        Profile with tuned stallGuard. Used for homing and printer0 move_tower.
        """

    @property
    @abstractmethod
    def moveFast(self) -> SingleProfile:
        """
        Former moveFast for all SL1,SL1S and M1
        """

    @property
    @abstractmethod
    def moveSlow(self) -> SingleProfile:
        """
        Former moveSlow for all SL1,SL1S and M1
        """

    @property
    @abstractmethod
    def resinSensor(self) -> SingleProfile:
        """
        Profile with tuned stallGuard. Used for resin measurements
        and cleaning wizard touch down phase. Using all printer models.
        """

    @property
    @abstractmethod
    def layer1(self) -> SingleProfile:
        """
        New profile for all printer models
        Max speed 1 mm/s.
        """

    @property
    @abstractmethod
    def layer2(self) -> SingleProfile:
        """
        Former superSlow for all SL1,SL1S and M1
        Max speed 2 mm/s.
        """

    @property
    @abstractmethod
    def layer3(self) -> SingleProfile:
        """
        New profile for all printer models
        Max speed 3 mm/s.
        """

    @property
    @abstractmethod
    def layer4(self) -> SingleProfile:
        """
        New profile for all printer models
        Max speed 4 mm/s.
        """

    @property
    @abstractmethod
    def layer5(self) -> SingleProfile:
        """
        New profile for all printer models
        Max speed 5 mm/s.
        """

    @property
    @abstractmethod
    def layer8(self) -> SingleProfile:
        """
        New profile for all printer models
        Max speed 8 mm/s.
        """

    @property
    @abstractmethod
    def layer11(self) -> SingleProfile:
        """
        New profile for all printer models
        Max speed 11 mm/s.
        """

    @property
    @abstractmethod
    def layer14(self) -> SingleProfile:
        """
        New profile for all printer models
        Max speed 14 mm/s.
        """

    @property
    @abstractmethod
    def layer18(self) -> SingleProfile:
        """
        New profile for all printer models
        Max speed 18 mm/s.
        """

    @property
    @abstractmethod
    def layer22(self) -> SingleProfile:
        """
        Former layer and layerMove for all SL1,SL1S and M1
        Max speed 22 mm/s.
        """

    @property
    @abstractmethod
    def layer24(self) -> SingleProfile:
        """
        New profile for all printer models
        Max speed 24 mm/s.
        """


class Tower(Axis):

    @property
    def name(self) -> str:
        return "tower"

    @property
    def sensitivity(self) -> int:
        return self._config.towerSensitivity

    @property
    def home_position(self) -> Nm:
        return self._config.tower_height_nm

    @property
    def config_height_position(self) -> Nm:
        return self.home_position

    @property
    def minimal_position(self) -> Nm:
        return Nm(0)

    @property
    def min_nm(self) -> Nm:
        return -Nm((self._config.default_tower_height_mm + 5) * 1_000_000)

    @property
    def above_surface_nm(self) -> Nm:
        return -Nm((self._config.default_tower_height_mm - 5) * 1_000_000)

    @property
    def max_nm(self) -> Nm:
        return Nm(2 * self._config.default_tower_height_mm * 1_000_000)

    @property
    def end_nm(self) -> Nm:
        return Nm(self._config.default_tower_height_mm * 1_000_000)

    @property
    def calib_pos_nm(self) -> Nm:
        return self._config.tower_calib_position_nm

    @property
    def resin_start_pos_nm(self) -> Nm:
        return self._config.tower_resin_measure_start_nm

    @property
    def resin_end_pos_nm(self) -> Nm:  # pylint: disable=no-self-use
        return self._config.tower_resin_measure_end_nm

    def _move_api_min(self) -> None:
        self.move(self._config.calib_tower_offset_nm)

    def _move_api_max(self) -> None:
        self.move(self._config.tower_height_nm)

    @staticmethod
    def _raise_move_failed():
        raise TowerMoveFailed()

    @staticmethod
    def _raise_home_failed():
        raise TowerHomeFailed()

    @property
    @abstractmethod
    def profiles(self) -> MovingProfilesTower:
        """all tower profiles"""
