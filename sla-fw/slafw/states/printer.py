# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2020 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from enum import unique, Enum
from typing import Iterable


@unique
class Printer0State(Enum):
    """
    General printer state enumeration
    """

    INITIALIZING = 0
    IDLE = 1
    # Replaced by state WIZARD, UNBOXING = 2
    WIZARD = 3
    # Replaced by state WIZARD, CALIBRATION = 4
    # Replaced by state WIZARD, DISPLAY_TEST = 5
    PRINTING = 6
    UPDATE = 7
    ADMIN = 8
    EXCEPTION = 9
    UPDATE_MC = 10
    OVERHEATED = 11


@unique
class PrinterState(Enum):
    INIT = 0
    RUNNING = 1
    PRINTING = 2
    UPDATING = 3
    ADMIN = 4
    WIZARD = 5
    UPDATING_MC = 6
    EXCEPTION = 7
    OVERHEATED = 9

    def to_state0(self) -> Printer0State:
        return {
            self.INIT: Printer0State.INITIALIZING,
            self.RUNNING: Printer0State.IDLE,
            self.EXCEPTION: Printer0State.EXCEPTION,
            self.UPDATING: Printer0State.UPDATE,
            self.PRINTING: Printer0State.PRINTING,
            self.WIZARD: Printer0State.WIZARD,
            self.UPDATING_MC: Printer0State.UPDATE_MC,
            self.ADMIN: Printer0State.ADMIN,
            self.OVERHEATED: Printer0State.OVERHEATED,
        }.get(self, None)  # type: ignore

    @staticmethod
    def get_most_important(states: Iterable[PrinterState]) -> PrinterState:
        if not states:
            return PrinterState.RUNNING

        s = sorted(states, key=lambda state: state.value)[-1]
        return s
