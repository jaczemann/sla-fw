# This file is part of the SLA firmware
# Copyright (C) 2020 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from dataclasses import dataclass
from enum import unique, Enum, auto
from typing import Optional


@unique
class TankSetup(Enum):
    PRINT = auto()  # Tank installed as if printing
    REMOVED = auto()  # Tank removed
    UV = auto()  # UV sensor installed


@unique
class PlatformSetup(Enum):
    REMOVED = auto()
    PRINT = auto()  # 0deg
    RESIN_TEST = auto()  # 60deg


@unique
class Resource(Enum):
    TILT = auto()
    TOWER = auto()
    TOWER_DOWN = auto()
    UV = auto()
    FANS = auto()
    MC = auto()

    def __lt__(self, other):
        return str(self) < str(other)


@dataclass
class Configuration:
    tank: Optional[TankSetup]
    platform: Optional[PlatformSetup]

    def is_compatible(self, other: Configuration):
        if not isinstance(other, Configuration):
            raise ValueError(f"The other configuration is not a configuration but \"{type(other)}\"")

        if self.tank and other.tank and self.tank != other.tank:
            return False

        if self.platform and other.platform and self.platform != other.platform:
            return False

        return True
