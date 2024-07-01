# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2019-2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from functools import cached_property
from unittest.mock import Mock

from slafw.hardware.exposure_screen import ExposureScreen, ExposureScreenParameters


class MockExposureScreen(ExposureScreen):
    # pylint: disable = too-few-public-methods
    # pylint: disable = too-many-instance-attributes
    def __init__(self, *_, **__):
        super().__init__()

        self.start = Mock()
        self.exit = Mock()
        self.show = Mock()
        self.blank_screen = Mock()
        self.create_areas = Mock()
        self.blank_area = Mock()
        self.draw_pattern = Mock()
        self.fake_usage_s = 3600

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

    def start_counting_usage(self):
        pass

    def stop_counting_usage(self):
        pass

    @property
    def usage_s(self) -> int:
        return self.fake_usage_s

    def save_usage(self):
        pass

    def clear_usage(self):
        self.fake_usage_s = 0
