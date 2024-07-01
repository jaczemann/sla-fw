# This file is part of the SLA firmware
# Copyright (C) 2020 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from enum import unique, Enum


@unique
class ExamplesState(Enum):
    INITIALIZING = 0
    DOWNLOADING = 1
    UNPACKING = 2
    COPYING = 3
    CLEANUP = 4
    COMPLETED = 5
    FAILURE = 6

    @staticmethod
    def get_finished():
        return [ExamplesState.COMPLETED, ExamplesState.FAILURE]
