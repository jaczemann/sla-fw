# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from enum import unique, Enum


@unique
class HardwareDeviceId(Enum):
    """
    Hardware device identifier, used to identify hardware part in an error messages
    """
    UV_LED_TEMP = 1000
    AMBIENT_TEMP = 1001
    CPU_TEMP = 1002

    UV_LED_FAN = 2000
    BLOWER_FAN = 2001
    REAR_FAN = 2002
