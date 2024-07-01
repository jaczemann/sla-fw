# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from enum import unique, Enum


@unique
class StatusBits(Enum):
    TOWER = 0
    TILT = 1
    BUTTON = 6
    COVER = 7
    ENDSTOP = 8
    RESET = 13
    FANS = 14
    FATAL = 15


@unique
class MotConComState(Enum):
    WRONG_BOARD_REVISION = -4
    UPDATE_FAILED = -3
    COMMUNICATION_FAILED = -2
    WRONG_FIRMWARE = -1
    OK = 0
    UV_LED_FAILED = 9
    UNKNOWN_ERROR = 999

    @classmethod
    def _missing_(cls, _value):
        return MotConComState.UNKNOWN_ERROR


@unique
class CommError(Enum):
    UNSPECIFIED_FAILURE = 1
    BUSY = 2
    SYNTAX_ERROR = 3
    PARAM_OUT_OF_RANGE = 4
    OPERATION_NOT_PERMITTED = 5
    NULL_POINTER = 6
    COMMAND_NOT_FOUND = 7

    @classmethod
    def _missing_(cls, _value):
        return CommError.UNSPECIFIED_FAILURE


@unique
class ResetFlags(Enum):
    UNKNOWN = -1
    POWER_ON = 0
    EXTERNAL = 1
    BROWN_OUT = 2
    WATCHDOG = 3
    JTAG = 4
    STACK_OVERFLOW = 7

    @classmethod
    def _missing_(cls, _value):
        return ResetFlags.UNKNOWN
