# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from abc import abstractmethod
from typing import Optional
from typing import List

from slafw.hardware.profiles import SingleProfile
from slafw.configs.value import IntValue
from slafw.hardware.axis import Axis
from slafw.errors.errors import MotionControllerException


class SingleProfileSL1(SingleProfile):
    starting_steprate = IntValue(minimum=0, maximum=22000, factory=True)
    maximum_steprate = IntValue(minimum=0, maximum=22000, factory=True)
    acceleration = IntValue(minimum=0, maximum=800, factory=True)
    deceleration = IntValue(minimum=0, maximum=800, factory=True)
    current = IntValue(minimum=0, maximum=63, factory=True)
    stallguard_threshold = IntValue(minimum=-128, maximum=127, factory=True)
    coolstep_threshold = IntValue(minimum=0, maximum=10000, factory=True)
    __definition_order__ = tuple(locals())


class AxisSL1(Axis):

    def __init__(self, config, power_led):
        super().__init__(config, power_led)
        self._actual_profile: Optional[SingleProfileSL1] = None

    def _move_api_get_profile(self, speed: int) -> SingleProfileSL1:
        if abs(speed) < 2:
            return self.profiles.homingSlow  # type: ignore
        return self.profiles.homingFast    # type: ignore

    def apply_profile(self, profile: SingleProfileSL1):
        if self.moving:
            raise MotionControllerException(f"Cannot edit profile while {self.name} is moving.", None)
        self.actual_profile = profile
        profile_data = self._read_profile_data()
        if self.actual_profile == profile_data:
            self._logger.debug("MC profile %s<%d> is up-to-date",
                    self._actual_profile.name, self._actual_profile.idx)
        else:
            self._logger.debug("Writing profile %s<%d> data %s to MC",
                    self._actual_profile.name, self._actual_profile.idx, list(self.actual_profile.dump()))
            self._write_profile_data()

    @property
    def actual_profile(self) -> SingleProfileSL1:
        mc_id = self._read_profile_id()
        if self._actual_profile.idx != mc_id:
            self._logger.warning("Wrong actual profile %d for %s, right one is %d",
                    self._actual_profile.idx, self.name, mc_id)
            try:
                self._actual_profile = self.profiles[mc_id]
            except IndexError:
                self._logger.error("Wrong profile index %d in MC", mc_id)   # TODO should we raise an exception?
        return self._actual_profile

    @actual_profile.setter
    def actual_profile(self, profile: SingleProfileSL1):
        """
        Write profile always to MC to prevent misconfigurations.
        """
        if self.moving:
            raise MotionControllerException(f"Cannot change profiles while {self.name} is moving.", None)
        self._write_profile_id(profile.idx)
        self._actual_profile = profile
        self._logger.debug("Profile set to %s<%d>", self._actual_profile.name, self._actual_profile.idx)
        if profile.idx == -1:
            self._logger.debug("Temporary profile, forcing profile data write")
            self._write_profile_data()

    @abstractmethod
    def _read_profile_id(self) -> int:
        pass

    @abstractmethod
    def _read_profile_data(self) -> List[int]:
        pass

    @abstractmethod
    def _write_profile_id(self, profile_id: int):
        pass

    @abstractmethod
    def _write_profile_data(self):
        pass

    def set_stepper_sensitivity(self, sensitivity: int):
        """ Profiles are not written to MC, call profiles.apply_all() manually """
        if sensitivity < -2 or sensitivity > 2:
            raise ValueError(f"{self.name} sensitivity must be from -2 to +2")
        hf = self.profiles.homingFast   # type: ignore
        hs = self.profiles.homingSlow   # type: ignore
        if hf.is_modified or hs.is_modified:
            raise RuntimeError(f"Can't set motor sensitivity for {self.name}, modified profile(s)")
        hf.current = self.sensitivity_dict["homingFast"][sensitivity+2][0]
        hf.stallguard_threshold = self.sensitivity_dict["homingFast"][sensitivity+2][1]
        hs.current = self.sensitivity_dict["homingSlow"][sensitivity+2][0]
        hs.stallguard_threshold = self.sensitivity_dict["homingSlow"][sensitivity+2][1]
        self._logger.info("%s profiles changed to: %s", self.name, self.profiles)
