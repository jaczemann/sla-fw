#!/usr/bin/env python3

# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import unittest
import numpy
from PIL import Image

from slafw import defines
from slafw.tests.base import SlafwTestCaseDBus
from slafw.project.functions import get_white_pixels
from slafw.image import cairo


class TestCairo(SlafwTestCaseDBus):
    FHD_SIZE = (1920, 1080)
    SL1_SIZE = (1440, 2560)
    SL1S_SIZE = (1620, 2560)

    def test_white(self):
        size = self.FHD_SIZE
        data = numpy.empty(shape=size, dtype=numpy.uint8)
        cairo.draw_white(data, *size)
        img = Image.frombytes("L", size, data)
        self.assertEqual(get_white_pixels(img), 2073600)

    def test_chess_8(self):
        size = self.SL1_SIZE
        data = numpy.empty(shape=size, dtype=numpy.uint8)
        cairo.draw_chess(data, *size, 8)
        img = Image.frombytes("L", size, data)
        self.assertSameImage(img, Image.open(self.SAMPLES_DIR / "cairo" / "chess8_sl1.png"))

    def test_chess_16(self):
        size = self.SL1S_SIZE
        data = numpy.empty(shape=size, dtype=numpy.uint8)
        cairo.draw_chess(data, *size, 16)
        img = Image.frombytes("L", size, data)
        self.assertSameImage(img, Image.open(self.SAMPLES_DIR / "cairo" / "chess16_sl1s.png"))

    def test_grid_8(self):
        size = self.SL1S_SIZE
        data = numpy.empty(shape=size, dtype=numpy.uint8)
        cairo.draw_grid(data, *size, 7, 1)
        img = Image.frombytes("L", size, data)
        self.assertSameImage(img, Image.open(self.SAMPLES_DIR / "cairo" / "grid8_sl1s.png"))

    def test_grid_16(self):
        size = self.SL1_SIZE
        data = numpy.empty(shape=size, dtype=numpy.uint8)
        cairo.draw_grid(data, *size, 14, 2)
        img = Image.frombytes("L", size, data)
        self.assertSameImage(img, Image.open(self.SAMPLES_DIR / "cairo" / "grid16_sl1.png"))

    def test_gradient_horizontal(self):
        size = self.FHD_SIZE
        data = numpy.empty(shape=size, dtype=numpy.uint8)
        cairo.draw_gradient(data, *size, False)
        img = Image.frombytes("L", size, data)
        self.assertSameImage(img, Image.open(self.SAMPLES_DIR / "cairo" / "gradient_h_fhd.png"))

    def test_gradient_vertical(self):
        size = self.FHD_SIZE
        data = numpy.empty(shape=size, dtype=numpy.uint8)
        cairo.draw_gradient(data, *size, True)
        img = Image.frombytes("L", size, data)
        self.assertSameImage(img, Image.open(self.SAMPLES_DIR / "cairo" / "gradient_v_fhd.png"))

    def test_inverse(self):
        size = self.FHD_SIZE
        data = numpy.empty(shape=size, dtype=numpy.uint8)
        cairo.draw_chess(data, *size, 16)
        cairo.inverse(data, *size)
        img = Image.frombytes("L", size, data)
        self.assertSameImage(img, Image.open(self.SAMPLES_DIR / "cairo" / "inverse_fhd.png"))

    def test_logo(self):
        size = self.SL1_SIZE
        data = numpy.empty(shape=size, dtype=numpy.uint8)
        cairo.draw_svg_expand(data, *size, defines.prusa_logo_file, True)
        img = Image.frombytes("L", size, data)
        self.assertSameImage(img, Image.open(self.SAMPLES_DIR / "cairo" / "logo_sl1.png"))

if __name__ == '__main__':
    unittest.main()
