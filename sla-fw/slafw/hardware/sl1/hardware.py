# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2019-2024 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

# TODO: Fix following pylint problems
# pylint: disable=too-many-lines
# pylint: disable=too-few-public-methods
# pylint: disable=too-many-instance-attributes
# pylint: disable=too-many-locals
# pylint: disable=too-many-public-methods
# pylint: disable=too-many-statements
# pylint: disable=too-many-branches
# pylint: disable=too-many-function-args

import asyncio
from asyncio import Task, CancelledError
from datetime import timedelta
from math import ceil
from threading import Thread
from time import sleep
from typing import Optional, Any

from slafw import defines
from slafw.configs.hw import HwConfig
from slafw.errors.errors import MotionControllerException
from slafw.functions.decorators import safe_call
from slafw.hardware.a64.temp_sensor import A64CPUTempSensor
from slafw.hardware.hardware import BaseHardware
from slafw.hardware.exposure_screen import VirtualExposureScreen
from slafw.hardware.printer_model import PrinterModel
from slafw.hardware.sl1.exposure_screen import SL1ExposureScreen, SL1SExposureScreen
from slafw.hardware.sl1.fan import SL1FanUVLED, SL1FanBlower, SL1FanRear
from slafw.hardware.sl1.power_led import PowerLedSL1
from slafw.hardware.sl1.temp_sensor import SL1TempSensorUV, SL1STempSensorUV, SL1TempSensorAmbient
from slafw.hardware.sl1.tilt import TiltSL1
from slafw.hardware.sl1.tower import TowerSL1
from slafw.hardware.sl1.uv_led import SL1UVLED, SL1SUVLED
from slafw.hardware.sl1.sl1s_uvled_booster import Booster
from slafw.motion_controller.sl1_controller import MotionControllerSL1
from slafw.motion_controller.value_checker import ValueChecker, UpdateInterval


class HardwareSL1(BaseHardware):
    def __init__(self, hw_config: HwConfig, printer_model: PrinterModel):
        super().__init__(hw_config, printer_model)

        self.mcc = MotionControllerSL1()
        self.sl1s_booster = Booster()

        if printer_model == PrinterModel.SL1:
            self.exposure_screen = SL1ExposureScreen(self.mcc)
        elif printer_model in (PrinterModel.SL1S, PrinterModel.M1):
            self.exposure_screen = SL1SExposureScreen(self.mcc)
        elif printer_model == PrinterModel.VIRTUAL:
            self.exposure_screen = VirtualExposureScreen()
        else:
            raise NotImplementedError

        self.config.add_onchange_handler(self._config_value_refresh)

        self._value_refresh_thread = Thread(daemon=True, target=self._value_refresh_body)
        self._value_refresh_task: Optional[Task] = None

        self.check_cover_override = False

        if printer_model in (PrinterModel.SL1, PrinterModel.VIRTUAL):
            self.uv_led_temp = SL1TempSensorUV(self.mcc, self.config)
        elif printer_model in (PrinterModel.SL1S, PrinterModel.M1):
            self.uv_led_temp = SL1STempSensorUV(self.mcc, self.config)
        else:
            raise NotImplementedError

        self.ambient_temp = SL1TempSensorAmbient(self.mcc)
        self.cpu_temp = A64CPUTempSensor()

        self.uv_led_fan = SL1FanUVLED(self.mcc, self.config, self.uv_led_temp)
        self.blower_fan = SL1FanBlower(self.mcc, self.config)
        self.rear_fan = SL1FanRear(self.mcc, self.config)

        if printer_model in (PrinterModel.SL1, PrinterModel.VIRTUAL):
            self.uv_led = SL1UVLED(self.mcc, self.uv_led_temp)
        elif printer_model in (PrinterModel.SL1S, PrinterModel.M1):
            self.uv_led = SL1SUVLED(self.mcc, self.sl1s_booster, self.uv_led_temp)
        else:
            raise NotImplementedError

        self.power_led = PowerLedSL1(self.mcc)
        self.tower = TowerSL1(self.mcc, self.config, self.power_led, printer_model)
        self.tilt = TiltSL1(self.mcc, self.config, self.power_led, self.tower, printer_model)

        self._tilt_position_checker = ValueChecker(
            lambda: self.tilt.position,
            self.tilt_position_changed,
            UpdateInterval.seconds(5),
            pass_value=False,
        )
        self._tower_position_checker = ValueChecker(
            lambda: self.tower.position,
            self.tower_position_changed,
            UpdateInterval.seconds(5),
            pass_value=False,
        )
        self.mcc.tilt_status_changed.connect(self._tilt_position_checker.set_rapid_update)
        self.mcc.tower_status_changed.connect(self._tower_position_checker.set_rapid_update)
        self.mcc.power_button_changed.connect(self.power_button_state_changed.emit)
        self.mcc.cover_state_changed.connect(self.cover_state_changed.emit)
        self.mcc.tower_status_changed.connect(lambda x: self.tower_position_changed.emit())
        self.mcc.tilt_status_changed.connect(lambda x: self.tilt_position_changed.emit())
        self.cpu_temp.overheat_changed.connect(self._cpu_overheat)

    # MUST be called before start()
    def connect(self):
        # MC have to be started first (beep, poweroff)
        self.mcc.connect(self.config.MCversionCheck)
        self.mc_sw_version_changed.emit()
        self.exposure_screen.start()

        if self.printer_model.options.has_booster:
            self.sl1s_booster.connect()

    def start(self):
        self.tower.start()
        self.tilt.start()
        self.initDefaults()
        self._value_refresh_thread.start()

    def exit(self):
        if self._value_refresh_thread.is_alive():
            while not self._value_refresh_task:
                sleep(0.1)
            self._value_refresh_task.cancel()
            self._value_refresh_thread.join()
        self.mcc.exit()
        self.exposure_screen.exit()

    async def _value_refresh_task_body(self):
        # This is deprecated, move value checkers to MotionControllerSL1
        checkers = [
            ValueChecker(self.getResinSensorState, self.resin_sensor_state_changed),
            self._tilt_position_checker,
            self._tower_position_checker,
            ValueChecker(self.mcc.getStateBits, None, UpdateInterval(timedelta(milliseconds=500))),
        ]

        tasks = [checker.check() for checker in checkers]

        # TODO: This is temporary
        # We should have a thread for running component services and get rid of the value checker thread
        tasks.extend([fan.run() for fan in self.fans.values()])
        tasks.append(self.cpu_temp.run())

        self._value_refresh_task = asyncio.gather(*tasks)
        await self._value_refresh_task

    def _value_refresh_body(self):
        try:
            asyncio.run(self._value_refresh_task_body())
        except CancelledError:
            pass  # This is normal printer shutdown
        except Exception:
            self.logger.exception("Value checker thread crashed")
            raise
        finally:
            self.logger.info("Value refresh checker thread ended")

    def _config_value_refresh(self, key: str, _: Any):
        """Re-load the fan RPM and stepper sensitivity settings from configuration, should be used as a callback"""
        if key in {"fan1Rpm", "fan2Rpm", "fan3Rpm", "fan1Enabled", "fan2Enabled", "fan3Enabled", }:
            self.uv_led_fan.default_rpm = self.config.fan1Rpm
            self.uv_led_fan.enabled = self.config.fan1Enabled
            self.blower_fan.default_rpm = self.config.fan2Rpm
            self.blower_fan.enabled = self.config.fan2Enabled
            self.rear_fan.default_rpm = self.config.fan3Rpm
            self.rear_fan.enabled = self.config.fan3Enabled

        if key == "tiltSensitivity":
            self.tilt.apply_all_profiles()

        if key == "towerSensitivity":
            self.tower.apply_all_profiles()

    def initDefaults(self):
        self.motors_release()
        self.uv_led.pwm = self.config.uvPwm
        self.power_led.intensity = self.config.pwrLedPwm
        self.resinSensor(False)
        self.stop_fans()
        self.tilt.movement_ended.connect(lambda: self._tilt_position_checker.set_rapid_update(False))

    def flashMC(self):
        self.mcc.flash()

    @property
    def mcFwVersion(self):
        return self.mcc.fw.version

    @property
    def mcFwRevision(self):
        return self.mcc.fw.revision

    @property
    def mcBoardRevision(self):
        if self.mcc.board.revision > -1 and self.mcc.board.subRevision != "":
            return f"{self.mcc.board.revision:d}{self.mcc.board.subRevision}"

        return "*INVALID*"

    @property
    def mcSerialNo(self):
        return self.mcc.board.serial

    def eraseEeprom(self):
        self.mcc.do("!eecl")
        self.mcc.soft_reset()  # FIXME MC issue

    def getStallguardBuffer(self):
        samplesList = []
        samplesCount = self.mcc.doGetInt("?sgbc")
        while samplesCount > 0:
            try:
                samples = self.mcc.doGetIntList("?sgbd", base=16)
                samplesCount -= len(samples)
                samplesList.extend(samples)
            except MotionControllerException:
                self.logger.exception("Problem reading stall guard buffer")
                break

        return samplesList

    def beep(self, frequency_hz: int, length_s: float):
        try:
            if not self.config.mute:
                self.mcc.do("!beep", frequency_hz, int(length_s * 1000))
        except MotionControllerException:
            self.logger.exception("Failed to beep")

    def beepRepeat(self, count):
        for _ in range(count):
            self.beep(1800, 0.1)
            sleep(0.5)

    def beepAlarm(self, count):
        for _ in range(count):
            self.beep(1900, 0.05)
            sleep(0.25)

    def resinSensor(self, state: bool):
        """Enable/Disable resin sensor"""
        self.mcc.do("!rsen", 1 if state else 0)

    def getResinSensor(self):
        """
        Read resin sensor enabled
        :return: True if enabled, False otherwise
        """
        return self.mcc.doGetBool("?rsen")

    def getResinSensorState(self) -> bool:
        """
        Read resin sensor value
        :return: True if resin is detected, False otherwise
        """
        return self.mcc.doGetBool("?rsst")

    @safe_call(False, MotionControllerException)
    def isCoverClosed(self, check_for_updates: bool = True) -> bool:
        return self.mcc.checkState("cover", check_for_updates)

    def isCoverVirtuallyClosed(self, check_for_updates: bool = True) -> bool:
        """
        Check whenever the cover is closed or cover check is disabled
        """
        return self.isCoverClosed(check_for_updates=check_for_updates) or not self.config.coverCheck

    def getPowerswitchState(self) -> bool:
        return self.mcc.checkState("button")

    def _cpu_overheat(self, overheat: bool):
        if overheat:
            self.logger.warning("Printer is overheating! Measured %.1f °C on A64.", self.cpu_temp.value)
            if not any(fan.enabled for fan in self.fans.values()):
                self.start_fans()
            # self.checkCooling = True #shouldn't this start the fan check also?

    # --- motors ---

    def motors_release(self) -> None:
        self.mcc.do("!motr")

    @safe_call(False, MotionControllerException)
    def motors_stop(self):
        self.mcc.do("!mot", 0)

    # --- tower ---

    # metal vat:
    #  5.0 mm -  35 % -  68.5 ml
    # 10.0 mm -  70 % - 137.0 ml
    # 14.5 mm - 100 % - 200.0 ml
    # 35 % -  70 % : 1.0 mm = 13.7 ml
    # 70 % - 100 % : 1.0 mm = 14.0 ml

    # plastic vat:
    #  4.5 mm -  35 % -  66.0 ml (mostly same as metal vat)
    # 10.0 mm -  70 % - 146.5 ml
    # 13.6 mm - 100 % - 200.0 ml
    # 35 % -  70 % : 1.0 mm = 14.65 ml
    # 70 % - 100 % : 1.0 mm = 14.85 ml

    def get_precise_resin_volume_ml(self) -> float:
        return asyncio.run(self.get_precise_resin_volume_ml_async())

    async def get_precise_resin_volume_ml_async(self) -> float:
        if self.config.vatRevision == 1:
            self.logger.debug("Using PLASTIC vat values")
            resin_constant = (14.65, 14.85)
        else:
            self.logger.debug("Using METALIC vat values")
            resin_constant = (13.7, 14.0)
        pos_mm = await self.get_resin_sensor_position_mm()
        if pos_mm < 10.0:
            volume = pos_mm * resin_constant[0]
        else:
            volume = pos_mm * resin_constant[1]
        return volume

    async def get_resin_volume_async(self) -> int:
        return int(round(await self.get_precise_resin_volume_ml_async() / 10.0) * 10)

    @staticmethod
    def calcPercVolume(volume_ml) -> int:
        return 10 * ceil(10 * volume_ml / defines.resinMaxVolume)

    @safe_call(0, MotionControllerException)
    async def get_resin_sensor_position_mm(self) -> float:
        await self.tower.move_ensure_async(self.tower.resin_start_pos_nm)
        try:
            self.resinSensor(True)
            await asyncio.sleep(1)
            self.tower.actual_profile = self.tower.profiles.resinSensor
            relative_move_nm = self.tower.resin_start_pos_nm - self.tower.resin_end_pos_nm
            self.mcc.do("!rsme", self.config.nm_to_tower_microsteps(relative_move_nm))
            await self.tower.wait_to_stop_async()
            if not self.getResinSensorState():
                self.logger.error("Resin sensor was not triggered")
                return 0.0
        finally:
            self.resinSensor(False)
        return float(self.tower.position) / 1_000_000
