# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import mmap
from unittest.mock import Mock
from tempfile import TemporaryFile

from slafw.hardware.exposure_screen import ExposureScreenParameters

class WaylandMock:
    # pylint: disable = too-many-instance-attributes
    # pylint: disable = too-few-public-methods
    def __init__(self, parameters: ExposureScreenParameters):
        self.start = Mock()
        self.exit = Mock()
        self.show_bytes = Mock()
        self.show_shm = Mock()
        self.blank_screen = Mock()
        self.create_areas = Mock()
        self.blank_area = Mock()

        self.main_layer = Mock()
        size = parameters.width_px * parameters.height_px * parameters.bytes_per_pixel
        with TemporaryFile() as tf:
            tf.truncate(size)
            self.main_layer.shm_data = mmap.mmap(
                tf.fileno(), size, prot=mmap.PROT_READ | mmap.PROT_WRITE, flags=mmap.MAP_SHARED
            )
        self.main_layer.width = parameters.width_px
        self.main_layer.height = parameters.height_px
        self.main_layer.bytes_per_pixel = parameters.bytes_per_pixel
