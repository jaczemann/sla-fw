# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2022 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest.mock import patch, Mock

from slafw.hardware.sl1.exposure_screen import SL1SExposureScreen, SL1ExposureScreen
from slafw.hardware.sl1.uv_led import SL1UVLED, SL1SUVLED
from slafw.tests.base import SlafwTestCase
from slafw.hardware.printer_model import PrinterModel
from slafw.hardware.exposure_screen import VirtualExposureScreen
from slafw.tests.mocks.motion_controller import MotionControllerMock
from slafw.tests.mocks.temp_sensor import MockTempSensor
from slafw.tests.mocks.uv_led import MockUVLED


class TestPrinterModel(SlafwTestCase):

    def test_name(self):
        model = PrinterModel.NONE
        self.assertEqual(model.name, "NONE")
        model = PrinterModel.SL1S
        self.assertEqual(model.name, "SL1S")

    def test_value(self):
        self.assertEqual(0, PrinterModel.NONE.value)
        self.assertEqual(1, PrinterModel.SL1.value)
        self.assertEqual(2, PrinterModel.SL1S.value)
        self.assertEqual(3, PrinterModel.M1.value)
        self.assertEqual(999, PrinterModel.VIRTUAL.value)

    def test_extensions(self):
        model = PrinterModel.NONE
        self.assertSetEqual({""}, model.extensions)
        model = PrinterModel.SL1S
        self.assertSetEqual({".sl1s"}, model.extensions)

    def test_exposure_screen_parameters_virtual(self):
        screen = VirtualExposureScreen()
        self.assertEqual((360, 640), screen.parameters.size_px)
        self.assertEqual(47250, screen.parameters.pixel_size_nm)
        self.assertEqual(0, screen.parameters.refresh_delay_ms)
        self.assertFalse(screen.parameters.monochromatic)
        self.assertFalse(screen.parameters.bgr_pixels)
        self.assertEqual(360, screen.parameters.width_px)
        self.assertEqual(640, screen.parameters.height_px)
        self.assertEqual((1440, 2560), screen.parameters.apparent_size_px)
        self.assertEqual(1440, screen.parameters.apparent_width_px)
        self.assertEqual(2560, screen.parameters.apparent_height_px)

    def test_exposure_screen_parameters_mock_sl1(self):
        screen = SL1ExposureScreen(Mock())
        self.assertEqual((1440, 2560), screen.parameters.size_px)
        self.assertEqual(47250, screen.parameters.pixel_size_nm)
        self.assertEqual(0, screen.parameters.refresh_delay_ms)
        self.assertFalse(screen.parameters.monochromatic)
        self.assertFalse(screen.parameters.bgr_pixels)
        self.assertEqual(1440, screen.parameters.width_px)
        self.assertEqual(2560, screen.parameters.height_px)
        self.assertEqual((1440, 2560), screen.parameters.apparent_size_px)

    def test_exposure_screen_parameters_sl1s(self):
        screen = SL1SExposureScreen(Mock())
        self.assertEqual((540, 2560), screen.parameters.size_px)
        self.assertEqual(50000, screen.parameters.pixel_size_nm)
        self.assertEqual(0, screen.parameters.refresh_delay_ms)
        self.assertTrue(screen.parameters.monochromatic)
        self.assertTrue(screen.parameters.bgr_pixels)
        self.assertEqual(540, screen.parameters.width_px)
        self.assertEqual(2560, screen.parameters.height_px)
        self.assertEqual((1620, 2560), screen.parameters.apparent_size_px)
        self.assertEqual(1620, screen.parameters.apparent_width_px)
        self.assertEqual(2560, screen.parameters.apparent_height_px)

    def test_options(self):
        options = PrinterModel.NONE.options
        self.assertFalse(options.has_tilt)
        self.assertFalse(options.has_booster)
        self.assertEqual(0, options.vat_revision)
        self.assertFalse(options.has_UV_calibration)
        self.assertFalse(options.has_UV_calculation)

    def test_uv_led_parameters_none(self):
        uv_led = MockUVLED()
        self.assertEqual(5, uv_led.parameters.intensity_error_threshold)
        self.assertEqual(0.75, uv_led.parameters.param_p)
        self.assertEqual(1, uv_led.parameters.min_pwm)
        self.assertEqual(250, uv_led.parameters.max_pwm)
        self.assertEqual(123, uv_led.parameters.safe_default_pwm)

    def test_uv_led_parameters_sl1(self):
        uv_led = SL1UVLED(MotionControllerMock.get_5a(), MockTempSensor("UV"))  # MC revision < 6c
        self.assertEqual(1, uv_led.parameters.intensity_error_threshold)
        self.assertEqual(0.75, uv_led.parameters.param_p)
        self.assertEqual(125, uv_led.parameters.min_pwm)
        self.assertEqual(218, uv_led.parameters.max_pwm)
        self.assertEqual(125, uv_led.parameters.safe_default_pwm)

    def test_uv_led_parameters_sl1_500khz(self):
        uv_led = SL1UVLED(MotionControllerMock.get_6c(), MockTempSensor("UV"))  # MC revision >= 6c
        self.assertEqual(1, uv_led.parameters.intensity_error_threshold)
        self.assertEqual(0.75, uv_led.parameters.param_p)
        self.assertEqual(150, uv_led.parameters.min_pwm)
        self.assertEqual(250, uv_led.parameters.max_pwm)
        self.assertEqual(150, uv_led.parameters.safe_default_pwm)

    def test_uv_led_parameters_sl1s(self):
        uv_led = SL1SUVLED(MotionControllerMock.get_6c(), Mock(), MockTempSensor("UV"))
        self.assertEqual(1, uv_led.parameters.intensity_error_threshold)
        self.assertEqual(0.75, uv_led.parameters.param_p)
        self.assertEqual(30, uv_led.parameters.min_pwm)
        self.assertEqual(250, uv_led.parameters.max_pwm)
        self.assertEqual(208, uv_led.parameters.safe_default_pwm)

    def test_exposure_screen_sn_transmittance_sl1s(self):
        self.exposure_screen_sn_transmittance(PrinterModel.SL1S)

    def test_exposure_screen_sn_transmittance_m1(self):
        self.exposure_screen_sn_transmittance(PrinterModel.M1)

    def exposure_screen_sn_transmittance(self, model: PrinterModel):
        hw_node = self.SAMPLES_DIR / "of_node" / model.name.lower()
        with patch("slafw.defines.exposure_panel_of_node", hw_node):
            screen = SL1SExposureScreen(Mock())
            self.assertEqual(4.17, screen.transmittance)
            self.assertEqual("CZPX0712X004X061939", screen.serial_number)
