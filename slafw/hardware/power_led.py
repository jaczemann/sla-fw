# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from enum import Enum
import logging
from abc import abstractmethod


class PowerLedActions(str, Enum):
    Normal = 'normal'
    Warning = 'warn'
    Error = 'error'
    Off = 'off'
    Unspecified = 'unspecified'


class PowerLed:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self._error_level_counter = 0
        self._warn_level_counter = 0

    @property
    @abstractmethod
    def mode(self) -> PowerLedActions:
        """returns current power led operation mode"""

    @mode.setter
    @abstractmethod
    def mode(self, value: PowerLedActions):
        """abstract mode setter"""

    @property
    @abstractmethod
    def intensity(self):
        """returns current power led brightness"""

    @intensity.setter
    @abstractmethod
    def intensity(self, pwm) -> int:
        """abstract intensity setter"""

    def set_error(self) -> int:
        if self._error_level_counter == 0:
            self.mode = PowerLedActions.Error
        self._error_level_counter += 1
        return self._error_level_counter

    def remove_error(self) -> int:
        if self._error_level_counter > 0:
            self._error_level_counter -= 1
        else:
            self.logger.warning("error_level_counter not greater than 0")
        if self._error_level_counter == 0:
            if self._warn_level_counter > 0:
                self.mode = PowerLedActions.Warning
            else:
                self.mode = PowerLedActions.Normal
        return self._error_level_counter

    def set_warning(self) -> int:
        if self._error_level_counter == 0 and self._warn_level_counter == 0:
            self.mode = PowerLedActions.Warning
        self._warn_level_counter += 1
        return self._warn_level_counter

    def remove_warning(self) -> int:
        if self._warn_level_counter > 0:
            self._warn_level_counter -= 1
        else:
            self.logger.warning("warn_level_counter not greater than 0")
        if self._error_level_counter == 0 and self._warn_level_counter == 0:
            self.mode = PowerLedActions.Normal
        return self._warn_level_counter

    def reset(self):
        self._warn_level_counter = 0
        self._error_level_counter = 0
        self.mode = PowerLedActions.Normal
