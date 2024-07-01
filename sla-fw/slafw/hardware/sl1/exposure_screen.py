# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Research a.s - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from abc import ABC
from functools import cached_property
from pathlib import Path

from slafw import defines
from slafw.hardware.exposure_screen import ExposureScreen, ExposureScreenParameters
from slafw.motion_controller.sl1_controller import MotionControllerSL1


class SL1xExposureScreen(ExposureScreen, ABC):
    def __init__(self, mcc: MotionControllerSL1):
        super().__init__()
        self._mcc = mcc
        self._mcc.statistics_changed.connect(self._on_statistics_changed)

    def start_counting_usage(self):
        self._mcc.do("!ulcd", 1)

    def stop_counting_usage(self):
        self._mcc.do("!ulcd", 0)

    @property
    def usage_s(self) -> int:
        data = self._mcc.doGetIntList("?usta")  # time counter [s] #TODO add uv average current, uv average temperature
        if len(data) != 2:
            raise ValueError(f"UV statistics data count not match! ({data})")
        return data[1]

    def save_usage(self):
        self._mcc.do("!usta", 0)

    def clear_usage(self):
        """
        Call if print display was replaced
        """
        self._mcc.do("!usta", 2)
        try:
            Path(defines.displayUsageData).unlink()
        except FileNotFoundError:
            pass

    def _on_statistics_changed(self, data):
        self.usage_s_changed.emit(data[1])


class SL1ExposureScreen(SL1xExposureScreen):
    @cached_property
    def parameters(self) -> ExposureScreenParameters:
        return ExposureScreenParameters(
            size_px=(1440, 2560),
            thumbnail_factor=5,
            output_factor=1,
            pixel_size_nm=47250,
            refresh_delay_ms=0,
            monochromatic=False,
            bgr_pixels=False,
        )


class SL1SExposureScreen(SL1xExposureScreen):
    @cached_property
    def parameters(self) -> ExposureScreenParameters:
        return ExposureScreenParameters(
            size_px=(540, 2560),
            thumbnail_factor=5,
            output_factor=1,
            pixel_size_nm=50000,
            refresh_delay_ms=0,
            monochromatic=True,
            bgr_pixels=True,
        )
