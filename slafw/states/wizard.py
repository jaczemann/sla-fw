# This file is part of the SLA firmware
# Copyright (C) 2020-2024 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from enum import unique, Enum


@unique
class WizardState(Enum):
    INIT = 0
    RUNNING = 1
    DONE = 2
    FAILED = 3
    CANCELED = 4
    STOPPED = 5

    # Group enter states - user printer reconfiguration
    PREPARE_WIZARD_PART_1 = 1000
    PREPARE_WIZARD_PART_2 = 1001
    PREPARE_WIZARD_PART_3 = 1002
    # PREPARE_CALIBRATION_PLATFORM_INSERT = 1010
    PREPARE_DISPLAY_TEST = 1011
    # PREPARE_CALIBRATION_TANK_PLACEMENT = 1012
    PREPARE_CALIBRATION_TILT_ALIGN = 1013
    PREPARE_CALIBRATION_PLATFORM_ALIGN = 1014
    PREPARE_CALIBRATION_FINISH = 1015
    PREPARE_CALIBRATION_INSERT_PLATFORM_TANK = 1016

    # User action required states
    CLOSE_COVER = 2000
    TEST_DISPLAY = 2001
    TEST_AUDIO = 2002
    LEVEL_TILT = 2003
    SHOW_RESULTS = 2004

    OPEN_COVER = 2100
    REMOVE_SAFETY_STICKER = 2101
    REMOVE_SIDE_FOAM = 2102
    REMOVE_TANK_FOAM = 2103  # Remove resin tank
    REMOVE_DISPLAY_FOIL = 2104  # Peel off exposure display foil
    INSERT_FOAM = 2105  # At factory reset, insert packing foams

    UV_CALIBRATION_PREPARE = 2200
    UV_CALIBRATION_PLACE_UV_METER = 2201
    UV_CALIBRATION_REMOVE_UV_METER = 2202
    UV_CALIBRATION_APPLY_RESULTS = 2203

    SL1S_CONFIRM_UPGRADE = 2300

    PREPARE_NEW_EXPO_PANEL = 2400

    TANK_SURFACE_CLEANER_INIT = 2500
    TANK_SURFACE_CLEANER_INSERT_CLEANING_ADAPTOR = 2501
    TANK_SURFACE_CLEANER_REMOVE_CLEANING_ADAPTOR = 2502

    @staticmethod
    def finished_states():
        return [WizardState.FAILED, WizardState.DONE, WizardState.CANCELED]


@unique
class WizardId(Enum):
    UNKNOWN = 0
    SELF_TEST = 1
    CALIBRATION = 2
    DISPLAY = 3
    COMPLETE_UNBOXING = 4
    KIT_UNBOXING = 5
    FACTORY_RESET = 6
    PACKING = 7
    UV_CALIBRATION = 8
    SL1S_UPGRADE = 9
    SL1_DOWNGRADE = 10
    NEW_EXPO_PANEL = 11
    TANK_SURFACE_CLEANER = 12


@unique
class WizardCheckState(Enum):
    WAITING = 0
    RUNNING = 1
    SUCCESS = 2
    FAILURE = 3
    WARNING = 4
    USER = 5
    CANCELED = 6
