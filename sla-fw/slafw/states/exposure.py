# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2020 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from enum import unique, Enum


@unique
class ExposureState(Enum):
    INIT = 0
    READING_DATA = 1
    CONFIRM = 2
    CHECKS = 3
    PRINTING = 5
    GOING_UP = 6
    GOING_DOWN = 7
    WAITING = 8
    COVER_OPEN = 9
    FEED_ME = 10
    FAILURE = 11
    STIRRING = 13
    PENDING_ACTION = 14
    FINISHED = 15
    STUCK = 16
    STUCK_RECOVERY = 17
    CHECK_WARNING = 22
    TILTING_DOWN = 24
    CANCELED = 26
    DONE = 27
    COOLING_DOWN = 28
    POUR_IN_RESIN = 29
    HOMING_AXIS = 30

    @staticmethod
    def finished_states():
        return [ExposureState.FAILURE, ExposureState.CANCELED, ExposureState.FINISHED, ExposureState.DONE]

    @staticmethod
    def cancelable_states():
        cancelable_states = ExposureState.finished_states()
        cancelable_states.extend((
            ExposureState.CONFIRM,
            ExposureState.CHECKS,
            ExposureState.POUR_IN_RESIN,
            ExposureState.HOMING_AXIS
        ))
        return cancelable_states


@unique
class ExposureCheck(Enum):
    # HARDWARE = 1 axis are homed separately
    TEMPERATURE = 2
    PROJECT = 3
    FAN = 4
    COVER = 5
    RESIN = 6
    START_POSITIONS = 7
    STIRRING = 8


@unique
class ExposureCheckResult(Enum):
    SCHEDULED = -1
    RUNNING = 0
    SUCCESS = 1
    FAILURE = 2
    WARNING = 3
    DISABLED = 4
