# This file is part of the SLA firmware
# Copyright (C) 2021-2024 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path
from unittest.mock import Mock

from PySignal import Signal

from slafw import defines
from slafw.configs.hw import HwConfig
from slafw.hardware.hardware import BaseHardware
from slafw.hardware.printer_model import PrinterModel
from slafw.tests.mocks.axis import MockTower, MockTilt
from slafw.tests.mocks.exposure_screen import MockExposureScreen
from slafw.tests.mocks.fan import MockFan
from slafw.tests.mocks.motion_controller import MotionControllerMock
from slafw.tests.mocks.temp_sensor import MockTempSensor
from slafw.tests.mocks.uv_led import MockUVLED


class HardwareMock(BaseHardware):
    # pylint: disable = too-many-instance-attributes
    # pylint: disable = no-self-use
    # pylint: disable = too-many-statements
    # pylint: disable = too-many-public-methods
    def __init__(self, config: HwConfig = None, printer_model: PrinterModel = PrinterModel.NONE):
        if config is None:
            config = HwConfig(Path("/tmp/dummyhwconfig.toml"), is_master=True)  # TODO better!
            config.coverCheck = False
        super().__init__(config, printer_model)
        self.config = config

        self.uv_led_temp = MockTempSensor(
            "UV LED",
            config.rpmControlUvLedMinTemp,
            config.rpmControlUvLedMaxTemp,
            critical=defines.maxUVTemp,
            hysteresis=defines.uv_temp_hysteresis,
            mock_value=Mock(return_value=46.7),
        )
        self.ambient_temp = MockTempSensor(
            "Ambient",
            minimal=defines.minAmbientTemp,
            maximal=defines.maxAmbientTemp,
            mock_value=Mock(return_value=26.1),
        )
        self.cpu_temp = MockTempSensor("CPU", mock_value=Mock(return_value=40))

        self.uv_led_fan = MockFan(
            "UV LED",
            defines.fanMinRPM,
            defines.fanMaxRPM,
            2000,
            reference=self.uv_led_temp,
            auto_control=self.config.rpmControlUvEnabled,
        )
        self.blower_fan = MockFan("UV LED", defines.fanMinRPM, defines.fanMaxRPM, 3300)
        self.rear_fan = MockFan("UV LED", defines.fanMinRPM, defines.fanMaxRPM, 1000)
        self.exposure_screen = MockExposureScreen()
        self.mcc = MotionControllerMock.get_6c()
        self.power_led = Mock()
        self.tower = MockTower(self.mcc, self.config, self.power_led, self.printer_model)
        self.tilt = MockTilt(self.mcc, self.config, self.power_led, self.printer_model)
        self.sl1s_booster = Mock()
        self.sl1s_booster.board_serial_no = "FAKE BOOSTER SERIAL"
        self.uv_led = MockUVLED()

        def update_expo_screen_usage(usage_s: int):
            if isinstance(self.exposure_screen, MockExposureScreen):
                self.exposure_screen.fake_usage_s += usage_s

        self.uv_led.usage_s_changed.connect(update_expo_screen_usage)

        self.cover_state_changed = Signal()
        self.mock_serial = "CZPX0819X009XC00151"
        self.mock_is_kit = False
        self.eth_mac = "10:9c:70:10:10:62"

    def motors_release(self) -> None:
        pass

    def read_cpu_serial(self):
        return self.mock_serial, self.mock_is_kit, self.eth_mac

    def exit(self):
        self.cover_state_changed.clear()

    def getPowerswitchState(self):
        return False

    @staticmethod
    def calcPercVolume(_):
        return 42

    def start_fans(self):
        for fan in self.fans.values():
            fan.running = True

    def connect(self):
        pass

    def start(self):
        pass

    def beep(self, frequency_hz: int, length_s: float):
        pass

    def getResinSensorState(self) -> bool:
        return True

    def isCoverClosed(self, check_for_updates: bool = True) -> bool:
        return True

    def isCoverVirtuallyClosed(self, check_for_updates: bool = True) -> bool:
        return True

    @property
    def mcFwVersion(self):
        return "1.0.0"

    @property
    def mcFwRevision(self):
        return 6

    @property
    def mcBoardRevision(self):
        return "6c"

    @property
    def mcSerialNo(self) -> str:
        return "CZPX0619X678XC12345"

    def eraseEeprom(self):
        pass

    async def get_resin_sensor_position_mm(self) -> float:
        return 12.8

    async def get_resin_volume_async(self) -> float:
        return defines.resinMaxVolume

    def flashMC(self):
        pass

    def initDefaults(self):
        pass

    def resinSensor(self, state: bool):
        pass

    def __reduce__(self):
        return (Mock, ())

    def __getattr__(self, name):
        setattr(self, name, Mock())
        return getattr(self, name)


def setupHw() -> HardwareMock:
    hw = HardwareMock(printer_model = PrinterModel.SL1)
    hw.connect()
    hw.start()
    hw.config.uvPwm = 250
    hw.config.calibrated = True
    return hw
