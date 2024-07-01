# This file is part of the SLA firmware
# Copyright (C) 2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Optional
from unittest.mock import Mock

from slafw.hardware.temp_sensor import TempSensor


class MockTempSensor(TempSensor):
    # pylint: disable = too-many-arguments
    def __init__(
        self,
        name: str,
        minimal: Optional[float] = None,
        maximal: Optional[float] = None,
        critical: Optional[float] = None,
        hysteresis: float = 0,
        mock_value: Mock = Mock(return_value=20),
    ):
        super().__init__(name, minimal, maximal, critical, hysteresis=hysteresis)
        self._mock_value = mock_value

    @property
    def value(self) -> float:
        return self._mock_value()
