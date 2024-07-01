# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Research a.s - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from abc import ABC
from asyncio import sleep
from functools import cached_property
from typing import Callable, Dict, Any, Tuple

from slafw.errors.errors import UVLEDsVoltagesDifferTooMuch, BoosterError, UVLEDsDisconnected, UVLEDsRowFailed
from slafw.hardware.temp_sensor import TempSensor
from slafw.hardware.uv_led import UVLED, UvLedParameters
from slafw.hardware.sl1.sl1s_uvled_booster import Booster
from slafw.motion_controller.sl1_controller import MotionControllerSL1


class UVLEDSL1x(UVLED, ABC):
    def __init__(self, mcc: MotionControllerSL1, uv_led_temp: TempSensor):
        super().__init__()
        self._mcc = mcc
        self._uv_led_temp = uv_led_temp
        self._mcc.statistics_changed.connect(self._on_statistics_changed)

    def on(self):
        self._check_overheat()
        self._mcc.do("!uled", 1, 0)
        self._logger.debug("UV on")

    def off(self):
        self._mcc.do("!uled", 0, 0)
        self._logger.debug("UV off")

    def pulse(self, time_ms: int):
        self._check_overheat()
        self._mcc.do("!uled", 1, time_ms + 1)  # FIXME workaround for MC FW (1 ms shorted UV LED time)
        self._logger.debug("UV on for %d ms", time_ms)

    @property
    def active(self) -> bool:
        return self._get_led_state()[0] == 1

    @property
    def pulse_remaining(self) -> int:
        return self._get_led_state()[1]

    def _get_led_state(self) -> Tuple[int, int]:
        data = self._mcc.doGetIntList("?uled")
        if not data:
            raise ValueError(f"UV data not valid: {data}")

        if len(data) == 1:
            return data[0], 0

        if len(data) == 2:
            return data[0], data[1]

        raise ValueError(f"UV data count not match! ({data})")

    @property
    def usage_s(self) -> int:
        data = self._mcc.doGetIntList("?usta")  # time counter [s] #TODO add uv average current, uv average temperature
        if len(data) != 2:
            raise ValueError(f"UV statistics data count not match! ({data})")
        return data[0]

    def save_usage(self):
        self._mcc.do("!usta", 0)

    def clear_usage(self):
        """
        Call if UV led was replaced
        """
        self._mcc.do("!usta", 1)

    @property
    def max_pwm(self) -> int:
        return 250 if self._is500khz else 219

    @property
    def info(self) -> Dict[str, Any]:
        return {
            # UV PWM set during this check
            "UV LED PWM": self.pwm,
        }

    @property
    def _is500khz(self) -> bool:
        if not isinstance(self._mcc.board.revision, int):
            raise ValueError(f"Board revision not a number: \"{self._mcc.board.revision}\"")
        return self._mcc.board.revision > 6 or (
            self._mcc.board.revision == 6 and self._mcc.board.subRevision == "c"
        )

    def _check_overheat(self):
        if self._uv_led_temp.overheat:
            raise Exception("Blocking attempt to set overheated UV LED on")

    def _on_statistics_changed(self, data):
        self.usage_s_changed.emit(data[0])


class SL1UVLED(UVLEDSL1x):
    VOLTAGE_REFRESH_WAIT_S = 5

    @property
    def pwm(self) -> int:
        return self._mcc.doGetInt("?upwm")

    @pwm.setter
    def pwm(self, value: int):
        self._mcc.do("!upwm", value)

    def read_voltages(self, precision=3):
        volts = self._mcc.doGetIntList("?volt", multiply=0.001)
        if len(volts) != 4:
            raise ValueError(f"Volts count not match! ({volts})")
        return [round(volt, precision) for volt in volts]

    @property
    def info(self) -> Dict[str, Any]:
        voltages = self.read_voltages()
        return super().info | {
            "UV LED Line 1 Voltage": voltages[0],
            "UV LED Line 2 Voltage": voltages[1],
            "UV LED Line 3 Voltage": voltages[2],
            "Power Supply Voltage": voltages[3],
        }  # type: ignore[operator]

    @cached_property
    def parameters(self) -> UvLedParameters:
        return UvLedParameters(
            min_pwm=150 if self._is500khz else 125,
            max_pwm=250 if self._is500khz else 218,
            safe_default_pwm=150 if self._is500khz else 125,
            intensity_error_threshold=1,
            param_p=0.75,
        )

    @cached_property
    def serial(self) -> str:
        return "NA"

    async def selftest(self, callback: Callable[[float], None] = None) -> Dict[str, Any]:
        self.pwm = 0
        self.on()
        if self._is500khz:
            uv_pwms = [40, 122, 243, self.max_pwm]  # board rev 0.6c+
        else:
            uv_pwms = [31, 94, 188, self.max_pwm]  # board rev. < 0.6c

        diff = 0.55  # [mV] voltages in all rows cannot differ more than this limit
        row1 = []
        row2 = []
        row3 = []
        try:  # check may be interrupted by another check or canceled
            for i, pwm in enumerate(uv_pwms):
                self.pwm = pwm
                SMOOTH_FACTOR = 50
                # wait to refresh all voltages (board rev. 0.6+)
                for j in range(SMOOTH_FACTOR):
                    if callback:
                        callback((i + (j / SMOOTH_FACTOR)) / len(uv_pwms))
                    await sleep(self.VOLTAGE_REFRESH_WAIT_S / SMOOTH_FACTOR)
                volts = list(self.read_voltages())
                del volts[-1]  # delete power supply voltage
                self._logger.info("UV voltages: %s", volts)
                if max(volts) - min(volts) > diff:
                    raise UVLEDsVoltagesDifferTooMuch(f"{max(volts) - min(volts)} (max - min) > {diff}")
                row1.append(int(volts[0] * 1000))
                row2.append(int(volts[1] * 1000))
                row3.append(int(volts[2] * 1000))
        finally:
            self.off()

        return super().info | {
            # data in mV for 1/6, 1/2, 1/1 of max PWM for MC board
            "wizardUvVoltageRow1": row1,
            # data in mV for 1/6, 1/2, 1/1 of max PWM for MC board
            "wizardUvVoltageRow2": row2,
            # data in mV for 1/6, 1/2, 1/1 of max PWM for MC board
            "wizardUvVoltageRow3": row3,
        }  # type: ignore[operator]


class SL1SUVLED(UVLEDSL1x):
    def __init__(self, mcc: MotionControllerSL1, booster: Booster, temp_sensor: TempSensor):
        super().__init__(mcc, temp_sensor)
        self._booster = booster

    @property
    def pwm(self) -> int:
        return self._booster.pwm

    @pwm.setter
    def pwm(self, value: int):
        self._booster.pwm = value

    @property
    def info(self) -> Dict[str, Any]:
        # booster serial is the only useful information
        # booster status() heavily depends on PWM and UV LED state
        # what about EEPROM content?
        return super().info | {
            "Booster serial": self._booster.board_serial_no,
        }   # type: ignore[operator]

    @cached_property
    def parameters(self) -> UvLedParameters:
        return UvLedParameters(
            min_pwm=30,
            max_pwm=250,
            safe_default_pwm=208,
            intensity_error_threshold=1,
            param_p=0.75,
        )

    @cached_property
    def serial(self) -> str:
        return self._booster.board_serial_no

    async def selftest(self, callback: Callable[[float], None] = None) -> Dict[str, Any]:
        try:  # check may be interrupted by another check or canceled
            # test DAC output comparator
            self.pwm = 40
            await sleep(0.25)
            callback(0.25)
            dac_state, led_states = self._booster.status()
            if dac_state:
                raise BoosterError("DAC not turned off")
            self.pwm = 80
            await sleep(0.25)
            dac_state, led_states = self._booster.status()
            if not dac_state:
                raise BoosterError("DAC not turned on")

            callback(0.5)

            # test LED status
            self.pwm = 20
            self.on()
            await sleep(0.5)
            dac_state, led_states = self._booster.status()
            if all(led_states):
                raise UVLEDsDisconnected()
            if any(led_states):
                raise UVLEDsRowFailed()
        finally:
            self.off()
        return super().info | {"Booster status": self._booster.status()}  # type: ignore[operator]
