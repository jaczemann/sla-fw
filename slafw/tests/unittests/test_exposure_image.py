#!/usr/bin/env python3

# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2024 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import unittest

import numpy
from PIL import Image

from slafw.hardware.printer_model import PrinterModel
from slafw.tests.base import SlafwTestCase, RefCheckTestCase
from slafw.configs.hw import HwConfig
from slafw.image.exposure_image import ExposureImage
from slafw.project.project import Project
from slafw import defines, test_runtime
from slafw.tests.mocks.hardware import HardwareMock


class TestScreen(SlafwTestCase, RefCheckTestCase):
    # pylint: disable=too-many-public-methods
    HW_CONFIG = SlafwTestCase.SAMPLES_DIR / "hardware.cfg"
    NUMBERS = SlafwTestCase.SAMPLES_DIR / "numbers.sl1"
    CALIBRATION = SlafwTestCase.SAMPLES_DIR / "Resin_calibration_object.sl1"
    CALIBRATION_LINEAR = SlafwTestCase.SAMPLES_DIR / "Resin_calibration_linear_object.sl1"
    ZABA = SlafwTestCase.SAMPLES_DIR / "zaba.png"

    def setUp(self):
        super().setUp()

        self.preview_file = self.TEMP_DIR / "live.png"
        self.display_usage = self.TEMP_DIR / "display_usage.npz"
        defines.livePreviewImage = str(self.preview_file)
        defines.displayUsageData = str(self.display_usage)
        test_runtime.testing = True
        hw_config = HwConfig(self.HW_CONFIG)
        hw_config.read_file()
        self.hw = HardwareMock(hw_config, PrinterModel.SL1)
        self.exposure_image = ExposureImage(self.hw)
        self.exposure_image.start()

    def tearDown(self):
        self.exposure_image.exit()
        files = [
            self.preview_file,
            self.display_usage,
        ]
        for file in files:
            if file.exists():
                file.unlink()
        # Make sure we do not leave ExposureImage instances behind
        # There is a test to ensure this does not happen in tests
        del self.exposure_image
        super().tearDown()

    def _create_project(self, project_file):
        return Project(self.hw, project_file)

    def test_basics(self):
        self.assertTrue(self.exposure_image.is_screen_black, "Test init")
        self.exposure_image.open_screen()
        self.assertFalse(self.exposure_image.is_screen_black, "Test open screen")

    def test_show_image(self):
        self.exposure_image.show_image_with_path(TestScreen.ZABA)
        self.assertSameImage(self.exposure_image.buffer, Image.open(self.ZABA))

    def test_mask(self):
        project = self._create_project(self.NUMBERS)
        self.exposure_image.new_project(project)
        self.exposure_image.preload_image(0)
        self.assertFalse(project.warnings)
        white_pixels = self.exposure_image.sync_preloader()
        self.assertEqual(233600, white_pixels)
        self.exposure_image.blit_image()
        self.assertSameImage(self.exposure_image.buffer, Image.open(self.SAMPLES_DIR / "fbdev" / "mask.png"))

    def test_display_usage(self):
        project = self._create_project(self.NUMBERS)
        self.exposure_image.new_project(project)
        self.exposure_image.preload_image(0)
        self.assertFalse(project.warnings)
        self.exposure_image.sync_preloader()
        self.exposure_image.save_display_usage()
        with numpy.load(self.display_usage) as npzfile:
            saved_data = npzfile['display_usage']
        with numpy.load(self.SAMPLES_DIR / "display_usage.npz") as npzfile:
            example_data = npzfile['display_usage']
        self.assertTrue(numpy.array_equal(saved_data, example_data))

    def test_calibration_calib_pad(self):
        project = self._create_project(self.CALIBRATION)
        project.exposure_time_ms = 4000
        self.exposure_image.new_project(project)
        self.exposure_image.preload_image(0)
        self.assertFalse(project.warnings)
        white_pixels = self.exposure_image.sync_preloader()
        self.assertEqual(1289032, white_pixels)
        self.exposure_image.blit_image()
        self.assertSameImage(self.exposure_image.buffer, Image.open(self.SAMPLES_DIR / "fbdev" / "calib_pad.png"))

    def test_calibration_calib(self):
        project = self._create_project(self.CALIBRATION)
        project.exposure_time_ms = 4000
        self.exposure_image.new_project(project)
        self.exposure_image.preload_image(10)
        self.assertFalse(project.warnings)
        white_pixels = self.exposure_image.sync_preloader()
        self.assertLess(abs(1166191 - white_pixels), 50)
        self.exposure_image.blit_image()
        self.assertSameImage(self.exposure_image.buffer, Image.open(self.SAMPLES_DIR / "fbdev" / "calib.png"), threshold=40)

    def test_calibration_fill(self):
        project = self._create_project(self.CALIBRATION)
        self.exposure_image.new_project(project)
        self.exposure_image.preload_image(0)
        self.assertFalse(project.warnings)
        self.exposure_image.sync_preloader()
        self.exposure_image.blit_image()
        for idx in range(8):
            self.exposure_image.fill_area(idx, idx * 32)
        self.assertSameImage(self.exposure_image.buffer, Image.open(self.SAMPLES_DIR / "fbdev" / "calib_fill.png"))

    def test_calibration_calib_pad_compact(self):
        project = self._create_project(self.CALIBRATION)
        project.calibrate_compact = True
        self.exposure_image.new_project(project)
        self.exposure_image.preload_image(0)
        self.assertFalse(project.warnings)
        white_pixels = self.exposure_image.sync_preloader()
        self.assertEqual(1114168, white_pixels)
        self.exposure_image.blit_image()
        self.assertSameImage(self.exposure_image.buffer, Image.open(self.SAMPLES_DIR / "fbdev" / "calib_pad_compact.png"))

    def test_calibration_calib_compact(self):
        project = self._create_project(self.CALIBRATION)
        project.calibrate_compact = True
        self.exposure_image.new_project(project)
        self.exposure_image.preload_image(10)
        self.assertFalse(project.warnings)
        white_pixels = self.exposure_image.sync_preloader()
        self.assertLess(abs(1126168 - white_pixels), 50)
        self.exposure_image.blit_image()
        self.assertSameImage(self.exposure_image.buffer, Image.open(self.SAMPLES_DIR / "fbdev" / "calib_compact.png"),
                             threshold=40)

    def test_calibration_fill_compact(self):
        project = self._create_project(self.CALIBRATION)
        project.calibrate_compact = True
        self.exposure_image.new_project(project)
        self.exposure_image.preload_image(0)
        self.assertFalse(project.warnings)
        self.exposure_image.sync_preloader()
        self.exposure_image.blit_image()
        for idx in range(8):
            self.exposure_image.fill_area(idx, idx * 32)
        self.assertSameImage(self.exposure_image.buffer, Image.open(self.SAMPLES_DIR / "fbdev" / "calib_fill_compact.png"))

    def test_calibration_calib_pad_10(self):
        project = self._create_project(self.CALIBRATION_LINEAR)
        self.exposure_image.new_project(project)
        self.exposure_image.preload_image(0)
        self.assertFalse(project.warnings)
        white_pixels = self.exposure_image.sync_preloader()
        self.assertLess(abs(3587460 - white_pixels), 50)
        self.exposure_image.blit_image()
        self.assertSameImage(self.exposure_image.buffer, Image.open(self.SAMPLES_DIR / "fbdev" / "calib_pad_10.png"))

    def test_calibration_calib_10(self):
        project = self._create_project(self.CALIBRATION_LINEAR)
        self.exposure_image.new_project(project)
        self.assertFalse(project.warnings)
        self.exposure_image.preload_image(10)
        white_pixels = self.exposure_image.sync_preloader()
        self.assertLess(abs(1780994 - white_pixels), 50)
        self.exposure_image.blit_image()
        self.assertSameImage(self.exposure_image.buffer, Image.open(self.SAMPLES_DIR / "fbdev" / "calib_10.png"), threshold=40)

    def test_calibration_fill_10(self):
        project = self._create_project(self.CALIBRATION_LINEAR)
        self.exposure_image.new_project(project)
        self.exposure_image.preload_image(0)
        self.assertFalse(project.warnings)
        self.exposure_image.sync_preloader()
        self.exposure_image.blit_image()
        for idx in range(10):
            self.exposure_image.fill_area(idx, idx * 32)
        self.assertSameImage(self.exposure_image.buffer, Image.open(self.SAMPLES_DIR / "fbdev" / "calib_fill_10.png"))

    def test_calibration_calib_pad_10_compact(self):
        project = self._create_project(self.CALIBRATION_LINEAR)
        project.calibrate_compact = True
        self.exposure_image.new_project(project)
        self.exposure_image.preload_image(0)
        self.assertFalse(project.warnings)
        white_pixels = self.exposure_image.sync_preloader()
        self.assertLess(abs(3361680 - white_pixels), 50)
        self.exposure_image.blit_image()
        self.assertSameImage(self.exposure_image.buffer, Image.open(self.SAMPLES_DIR / "fbdev" / "calib_pad_10_compact.png"))

    def test_calibration_calib_10_compact(self):
        project = self._create_project(self.CALIBRATION_LINEAR)
        project.calibrate_compact = True
        self.exposure_image.new_project(project)
        self.exposure_image.preload_image(10)
        self.assertFalse(project.warnings)
        white_pixels = self.exposure_image.sync_preloader()
        self.assertLess(abs(1728640 - white_pixels), 50)
        self.exposure_image.blit_image()
        self.assertSameImage(self.exposure_image.buffer, Image.open(self.SAMPLES_DIR / "fbdev" / "calib_10_compact.png"), threshold=40)

    def test_calibration_fill_10_compact(self):
        project = self._create_project(self.CALIBRATION_LINEAR)
        project.calibrate_compact = True
        self.exposure_image.new_project(project)
        self.exposure_image.preload_image(0)
        self.assertFalse(project.warnings)
        self.exposure_image.sync_preloader()
        self.exposure_image.blit_image()
        for idx in range(10):
            self.exposure_image.fill_area(idx, idx * 32)
        self.assertSameImage(self.exposure_image.buffer, Image.open(self.SAMPLES_DIR / "fbdev" / "calib_fill_10_compact.png"))

if __name__ == '__main__':
    unittest.main()
