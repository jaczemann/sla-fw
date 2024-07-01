# This file is part of the SLA firmware
# Copyright (C) 2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import random
from datetime import datetime
from typing import List
from unittest.mock import Mock

import numpy

from slafw.libUvLedMeterMulti import UvCalibrationData
from slafw.tests.mocks.hardware import HardwareMock


class UVMeterMock:
    def __init__(self, hw: HardwareMock):
        self.check_place = Mock(return_value=None)
        self.present = Mock(return_value=True)
        self.connect = Mock()
        self._hw = hw
        self.multiplier = 1
        self.noise = 0
        self.sixty_points = False

    def __call__(self, *args, **kwargs):
        return self

    def read_data(self):
        data = UvCalibrationData()
        data.uvSensorType = 0
        data.uvSensorData = self.get_intensity_data()
        data.uvTemperature = 24.2
        data.uvDateTime = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        data.uvMean = float(numpy.mean(data.uvSensorData))

        data.uvStdDev = numpy.std(data.uvSensorData)
        data.uvMinValue = min(data.uvSensorData)
        data.uvMaxValue = max(data.uvSensorData)
        data.uvPercDiff = [(d - data.uvMean) / data.uvMean * 100 for d in data.uvSensorData]
        data.uvFoundPwm = -1
        return data

    def get_intensity_data(self) -> List[float]:
        # Linear response
        # 140 intensity at 200 PWM
        intensity = 140 * self.multiplier * self._hw.uv_led.pwm / 200
        print(f"UV intensity mock: pwm: {self._hw.uv_led.pwm}, intensity: {intensity}")
        random.seed(0)
        return [intensity + random.random() * 2 * self.noise - self.noise for _ in range(15)]

    def close(self):
        pass
