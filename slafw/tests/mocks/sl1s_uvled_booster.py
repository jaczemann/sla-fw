# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later
from typing import Tuple, List
from unittest.mock import Mock


class BoosterMock(Mock):
    _pwm = 0

    def status(self) -> Tuple[bool, List]:
        return bool(self._pwm > 60), [False, False, False]

    @property
    def pwm(self) -> int:
        return self._pwm

    @pwm.setter
    def pwm(self, pwm: int) -> None:
        self._pwm = pwm

    @property
    def board_serial_no(self) -> str:
        return "booster SN"
