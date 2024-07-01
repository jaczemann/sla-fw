# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Optional

from slafw.hardware.fan import Fan
from slafw.hardware.temp_sensor import TempSensor
from slafw.configs.writer import ConfigWriter


class MockFan(Fan):
    # pylint: disable = too-many-arguments
    def __init__(
        self,
        name,
        min_rpm: int,
        max_rpm: int,
        default_rpm: int,
        reference: Optional[TempSensor] = None,
        auto_control: bool = False,
    ):
        super().__init__(name, min_rpm, max_rpm, default_rpm, False, reference=reference, auto_control=auto_control)
        self._target_rpm = default_rpm

    def save(self, writer: ConfigWriter):
        pass

    @property
    def _running(self):
        pass

    @_running.setter
    def _running(self, value: bool):
        pass

    @property
    def rpm(self) -> int:
        return self._target_rpm

    @property
    def error(self) -> bool:
        return False

    @property
    def target_rpm(self) -> int:
        return self._target_rpm

    @target_rpm.setter
    def target_rpm(self, value: bool):
        self._target_rpm = value
