# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

# pylint: disable=too-many-public-methods
import unittest
from time import sleep
from typing import Optional, List
from unittest.mock import PropertyMock, patch

from slafw import defines
from slafw.configs.hw import HwConfig
from slafw.hardware.a64.temp_sensor import A64CPUTempSensor
from slafw.hardware.sl1.hardware import HardwareSL1
from slafw.hardware.sl1.uv_led import SL1UVLED
from slafw.hardware.power_led import PowerLedActions
from slafw.hardware.printer_model import PrinterModel
from slafw.tests.base import SlafwTestCase


class TestSL1Hardware(SlafwTestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hw_config: Optional[HwConfig] = None
        self.hw: Optional[HardwareSL1] = None

    def setUp(self):
        super().setUp()

        A64CPUTempSensor.CPU_TEMP_PATH.write_text("53500", encoding="utf-8")
        self.hw_config = HwConfig(file_path=self.SAMPLES_DIR / "hardware.cfg", is_master=True)
        self.hw = HardwareSL1(self.hw_config, PrinterModel.SL1)

        try:
            self.hw.connect()
            self.hw.start()
        except Exception as exception:
            self.tearDown()
            raise exception

    def tearDown(self):
        self.hw.exit()

        if self.EEPROM_FILE.exists():
            self.EEPROM_FILE.unlink()
        super().tearDown()

    def patches(self) -> List[patch]:
        return super().patches() + [
            patch("slafw.motion_controller.sl1_controller.MotionControllerSL1.TEMP_UPDATE_INTERVAL_S", 0.1),
            patch("slafw.motion_controller.sl1_controller.MotionControllerSL1.FAN_UPDATE_INTERVAL_S", 0.1),
            patch("slafw.hardware.fan.Fan.AUTO_CONTROL_INTERVAL_S", 0.1),
            patch("slafw.defines.cpuSNFile", str(self.SAMPLES_DIR / "nvmem")),
            patch("slafw.hardware.a64.temp_sensor.A64CPUTempSensor.CPU_TEMP_PATH", self.TEMP_DIR / "cputemp"),
            patch("slafw.defines.counterLog", str(self.TEMP_DIR / "uvcounter-log.json")),
        ]

    def test_cpu_read(self):
        self.assertEqual("CZPX0819X009XC00151", self.hw.cpuSerialNo)

    def test_eth_mac_read(self):
        self.assertEqual("10:9c:70:10:10:62", self.hw.ethMac)

    def test_info_read(self):
        self.assertRegex(self.hw.mcFwVersion, r"^\d+\.\d+\.\d+[a-zA-Z0-9-+.]*$")
        self.assertEqual("CZPX0619X678XC12345", self.hw.mcSerialNo)
        self.assertEqual(6, self.hw.mcFwRevision)
        self.assertEqual("6c", self.hw.mcBoardRevision)

    def test_uv_led(self):
        # Default state
        self.assertEqual(0, self.hw.uv_led.active)
        self.assertEqual(0, self.hw.uv_led.pulse_remaining)
        sleep(1)

        # Active state
        self.hw.uv_led.pulse(10000)
        self.assertEqual(1, self.hw.uv_led.active)
        self.assertGreater(self.hw.uv_led.pulse_remaining, 5000)

        # Current settings
        pwm = 233
        self.hw.uv_led.pwm = pwm
        self.assertEqual(pwm, self.hw.uv_led.pwm)

    # TODO: Fix test / functionality
    def test_mcc_debug(self):
        pass

    def test_erase(self):
        self.hw.eraseEeprom()

    def test_stallguard_buffer(self):
        self.assertEqual([], self.hw.getStallguardBuffer())

    def test_beeps(self):
        self.hw.beep(1024, 3)
        self.hw.beepEcho()
        self.hw.beepRepeat(3)
        self.hw.beepAlarm(3)

    def test_power_led_mode_normal(self):
        power_led_mode = PowerLedActions.Normal
        self.hw.power_led.mode = power_led_mode
        self.assertEqual(power_led_mode, self.hw.power_led.mode)

    def test_power_led_intensity(self):
        power_led_pwm = 100
        self.hw.power_led.intensity = power_led_pwm
        self.assertEqual(power_led_pwm, self.hw.power_led.intensity)

    def test_power_led_mode_warning(self):
        self.hw.power_led.mode = PowerLedActions.Warning
        self.assertEqual(PowerLedActions.Warning, self.hw.power_led.mode)

    def test_power_led_error(self):
        self.assertEqual(1, self.hw.power_led.set_error())
        self.assertEqual(PowerLedActions.Error, self.hw.power_led.mode)
        self.assertEqual(2, self.hw.power_led.set_error())
        self.assertEqual(PowerLedActions.Error, self.hw.power_led.mode)
        self.assertEqual(1, self.hw.power_led.remove_error())
        self.assertEqual(PowerLedActions.Error, self.hw.power_led.mode)
        self.assertEqual(0, self.hw.power_led.remove_error())
        self.assertEqual(PowerLedActions.Normal, self.hw.power_led.mode)

    def test_power_led_warning(self):
        self.assertEqual(1, self.hw.power_led.set_warning())
        self.assertEqual(PowerLedActions.Warning, self.hw.power_led.mode)
        self.assertEqual(2, self.hw.power_led.set_warning())
        self.assertEqual(PowerLedActions.Warning, self.hw.power_led.mode)
        self.assertEqual(1, self.hw.power_led.remove_warning())
        self.assertEqual(PowerLedActions.Warning, self.hw.power_led.mode)
        self.assertEqual(0, self.hw.power_led.remove_warning())
        self.assertEqual(PowerLedActions.Normal, self.hw.power_led.mode)

    def test_power_led_mixed(self):
        self.assertEqual(1, self.hw.power_led.set_warning())
        self.assertEqual(PowerLedActions.Warning, self.hw.power_led.mode)
        self.assertEqual(1, self.hw.power_led.set_error())
        self.assertEqual(PowerLedActions.Error, self.hw.power_led.mode)
        self.assertEqual(2, self.hw.power_led.set_warning())
        self.assertEqual(PowerLedActions.Error, self.hw.power_led.mode)
        self.assertEqual(0, self.hw.power_led.remove_error())
        self.assertEqual(PowerLedActions.Warning, self.hw.power_led.mode)
        self.assertEqual(1, self.hw.power_led.remove_warning())
        self.assertEqual(PowerLedActions.Warning, self.hw.power_led.mode)
        self.assertEqual(0, self.hw.power_led.remove_warning())
        self.assertEqual(PowerLedActions.Normal, self.hw.power_led.mode)

    def test_uv_statistics(self):
        # clear any garbage
        self.hw.uv_led.clear_usage()
        self.hw.exposure_screen.clear_usage()

        self.assertEqual(0, self.hw.uv_led.usage_s)
        self.assertEqual(0, self.hw.exposure_screen.usage_s)
        self.hw.uv_led.pulse(1000)
        sleep(1)
        self.assertEqual(1, self.hw.uv_led.usage_s)
        self.assertEqual(1, self.hw.exposure_screen.usage_s)
        self.hw.uv_led.clear_usage()
        self.assertEqual(0, self.hw.uv_led.usage_s)
        self.assertEqual(1, self.hw.exposure_screen.usage_s)
        self.hw.exposure_screen.clear_usage()
        self.assertEqual(0, self.hw.uv_led.usage_s)
        self.assertEqual(0, self.hw.exposure_screen.usage_s)

    def test_uv_display_counter(self):
        self.hw.uv_led.off()
        # clear any garbage
        self.hw.uv_led.clear_usage()
        self.hw.exposure_screen.clear_usage()

        self.assertEqual(0, self.hw.uv_led.usage_s)
        self.assertEqual(0, self.hw.exposure_screen.usage_s)
        uv_stats = self.hw.uv_led.usage_s
        display_stats = self.hw.exposure_screen.usage_s
        sleep(1)
        self.assertEqual(0, uv_stats)
        self.assertGreater(1, display_stats)
        self.hw.exposure_screen.stop_counting_usage()
        uv_stats = self.hw.uv_led.usage_s
        display_stats = self.hw.exposure_screen.usage_s
        sleep(1)
        self.assertEqual(uv_stats, self.hw.uv_led.usage_s)
        self.assertEqual(display_stats, self.hw.exposure_screen.usage_s)

    def test_voltages(self):
        if not isinstance(self.hw.uv_led, SL1UVLED):
            return

        voltages = self.hw.uv_led.read_voltages()
        self.assertEqual(4, len(voltages))
        for voltage in voltages:
            self.assertEqual(float, type(voltage))

    def test_resin_sensor(self):
        self.assertFalse(self.hw.getResinSensorState())
        self.hw.resinSensor(True)
        self.assertTrue(self.hw.getResinSensor())

        self.assertFalse(self.hw.getResinSensorState())

        # self.assertEqual(42, self.hw.get_resin_volume())

        self.assertEqual(80, self.hw.calcPercVolume(150))

    def test_cover_closed(self):
        self.assertFalse(self.hw.isCoverClosed())

    def test_power_switch(self):
        self.assertFalse(self.hw.getPowerswitchState())

    def test_fans(self):
        self.assertFalse(self.hw.mcc.checkState('fans'))

        for fan in self.hw.fans.values():
            fan.enabled = True

        self.hw.stop_fans()
        sleep(1)  # Wait for fans to stabilize and MC to report RPMs
        for fan in self.hw.fans.values():
            self.assertFalse(fan.error)

        # RPMs
        for fan in self.hw.fans.values():
            self.assertEqual(0, fan.rpm)

        self.hw.start_fans()
        sleep(1)  # Wait for fans to stabilize and MC to report RPMs
        self.assertLessEqual(self.hw.config.fan1Rpm, self.hw.uv_led_fan.rpm)  # due to rounding
        self.assertLessEqual(self.hw.config.fan2Rpm, self.hw.blower_fan.rpm)  # due to rounding
        self.assertLessEqual(self.hw.config.fan3Rpm, self.hw.rear_fan.rpm)  # due to rounding

        # Setters
        self.assertEqual(3, len(self.hw.fans))
        for key, value in self.hw.fans.items():
            # max RPM
            value.target_rpm = defines.fanMaxRPM[key]
            self.assertEqual(defines.fanMaxRPM[key], value.target_rpm)
            self.assertEqual(True, value.enabled)

            # min RPM
            value.target_rpm = defines.fanMinRPM
            self.assertEqual(defines.fanMinRPM, value.target_rpm)
            self.assertEqual(True, value.enabled)

            # below min RPM (adapted)
            value.target_rpm = defines.fanMinRPM - 1
            self.assertEqual(defines.fanMinRPM, value.target_rpm)

            # above max RPM (adapted)
            value.target_rpm = defines.fanMaxRPM[key] + 1
            self.assertEqual(defines.fanMaxRPM[key], value.target_rpm)

    def test_uv_fan_rpm_control(self):
        self.hw.uv_led_fan.enabled = True
        self.hw.uv_led_fan.running = True
        sleep(1)
        self.hw.uv_led_fan.auto_control = False
        sleep(1)
        self.assertEqual(self.hw.uv_led_fan.rpm, self.hw.uv_led_fan.rpm)
        self.hw.uv_led_fan.auto_control = True
        type(self.hw.uv_led_temp).value = PropertyMock(return_value=self.hw_config.rpmControlUvLedMinTemp)
        sleep(1)  # Wait for fans to stabilize
        self.assertGreaterEqual(self.hw.uv_led_fan.rpm, self.hw_config.rpmControlUvFanMinRpm)
        # due to rounding in MC
        type(self.hw.uv_led_temp).value = PropertyMock(return_value=self.hw_config.rpmControlUvLedMaxTemp)
        sleep(1)  # Wait for fans to stabilize
        # due to rounding in MC
        self.assertGreaterEqual(self.hw.uv_led_fan.rpm, self.hw_config.rpmControlUvFanMaxRpm)

    def test_temperatures(self):
        sleep(1)  # Wait for MC to report temp values
        self.assertGreaterEqual(self.hw.uv_led_temp.value, 0)
        self.assertGreaterEqual(self.hw.ambient_temp.value, 0)
        self.assertEqual(53.5, self.hw.cpu_temp.value)
        # TODO: This is weak test, The simulated value seems random 0, 52, 58, 125


if __name__ == '__main__':
    unittest.main()
