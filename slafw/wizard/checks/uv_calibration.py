# This file is part of the SLA firmware
# Copyright (C) 2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from abc import ABC
from asyncio import sleep, Queue, AbstractEventLoop, CancelledError, get_running_loop
from dataclasses import asdict
from datetime import datetime
from functools import partial
from typing import Dict, Any

import toml

from slafw import defines, test_runtime
from slafw.configs.stats import TomlConfigStats
from slafw.errors.errors import (
    FailedToDetectUVMeter,
    UVMeterFailedToRespond,
    UVMeterCommunicationFailed,
    ScreenTranslucent,
    UnexpectedUVIntensity,
    UnknownUVMeasurementFailure,
    UVTooDimm,
    UVTooBright,
    UVDeviationTooHigh,
    UVCalibrationError,
    FailedToSaveFactoryConfig,
)
from slafw.functions.files import save_wizard_history
from slafw.functions.system import FactoryMountedRW
from slafw.libUvLedMeterMulti import UvLedMeterMulti, UvMeterState, UVCalibrationResult
from slafw.states.wizard import WizardState
from slafw.wizard.data_package import WizardDataPackage
from slafw.wizard.actions import UserActionBroker, PushState
from slafw.wizard.checks.base import WizardCheckType, DangerousCheck, Check
from slafw.wizard.setup import Configuration, Resource

# pylint: disable = too-many-arguments


class CheckUVMeter(DangerousCheck):
    def __init__(self, package: WizardDataPackage, uv_meter: UvLedMeterMulti):
        super().__init__(package, WizardCheckType.UV_METER_PRESENT, Configuration(None, None), [Resource.UV])
        self._uv_meter = uv_meter

    async def async_task_run(self, actions: UserActionBroker):
        await self.wait_cover_closed()

        for i in range(0, defines.uvLedMeterMaxWait_s, -1):
            self.progress = i / defines.uvLedMeterMaxWait_s
            if self._uv_meter.present:
                break
            await sleep(1)

        if not self._uv_meter.present:
            raise FailedToDetectUVMeter()
        self._logger.info("UV meter device found")

        if not self._uv_meter.connect():
            # TODO: Move exception raise to connect
            raise UVMeterFailedToRespond()


class UVWarmupCheck(DangerousCheck):
    def __init__(self, package: WizardDataPackage):
        super().__init__(package, WizardCheckType.UV_WARMUP, Configuration(None, None), [Resource.UV, Resource.FANS])

    async def async_task_run(self, actions: UserActionBroker):
        hw = self._package.hw
        await self.wait_cover_closed()

        try:
            hw.start_fans()
            hw.uv_led.pwm = hw.uv_led.parameters.max_pwm
            self._package.exposure_image.blank_screen()
            hw.uv_led.on()

            for countdown in range(hw.config.uvWarmUpTime):
                self.progress = countdown / hw.config.uvWarmUpTime
                if test_runtime.testing:
                    await sleep(0.01)
                else:
                    await sleep(1)
        except (Exception, CancelledError):
            hw.uv_led.off()
            hw.stop_fans()
            raise

        hw.uv_led.pwm = hw.uv_led.parameters.min_pwm


class CheckUVMeterPlacement(DangerousCheck):
    def __init__(self, package: WizardDataPackage, uv_meter: UvLedMeterMulti):
        super().__init__(
            package, WizardCheckType.UV_METER_PLACEMENT, Configuration(None, None), [Resource.UV, Resource.FANS]
        )
        self._uv_meter = uv_meter

    async def async_task_run(self, actions: UserActionBroker):
        await self.wait_cover_closed()
        try:
            # NOTE: Fans and UV already started by previous check
            error = self._uv_meter.check_place(self._package.exposure_image.open_screen)
            # TODO: Move raise to check_place ?

            if error == UvMeterState.ERROR_COMMUNICATION:
                raise UVMeterCommunicationFailed()
            if error == UvMeterState.ERROR_TRANSLUCENT:
                raise ScreenTranslucent()
            if error == UvMeterState.ERROR_INTENSITY:
                raise UnexpectedUVIntensity()
            if error:
                raise UnknownUVMeasurementFailure(error)
        except (Exception, CancelledError):
            self._package.hw.uv_led.off()
            self._package.hw.stop_fans()
            raise


class UVCalibrate(DangerousCheck, ABC):
    # pylint: disable = too-many-instance-attributes
    INTENSITY_DEVIATION_THRESHOLD = 25
    SECOND_PASS_THRESHOLD = 240
    BOOST_MULTIPLIER = 1.2

    def __init__(
        self,
        check_type: WizardCheckType,
        package: WizardDataPackage,
        uv_meter: UvLedMeterMulti,
        result: UVCalibrationResult,
        replacement: bool,
    ):
        super().__init__(package, check_type, Configuration(None, None), [Resource.UV])
        self._uv_meter = uv_meter
        self._calibration_params = self._package.hw.uv_led.parameters
        self._result: UVCalibrationResult = result

        self.pwm = None
        self.intensity = None
        self.min_value = None
        self.deviation = 2 * self.INTENSITY_DEVIATION_THRESHOLD
        self.result = None

        self.factoryUvPwm = self._package.hw.config.data_factory_values["uvPwm"]
        if not self.factoryUvPwm:
            self._logger.error("Factory UV PWM == 0, not set yet")

        if replacement or not self.factoryUvPwm:
            # if user replaced HW component allow UV PWM up to 240 without boost
            self.factoryUvPwm = 200
            self._logger.info("Using temporary default factoryUvPwm %s.", self.factoryUvPwm)
            self._logger.info("Result will be written into factory partition.")


class UVCalibrateCenter(UVCalibrate):
    PARAM_I = 0.0025
    # TODO: Do not wait for fixed number of iterations. Check the results continuously.
    TUNING_ITERATIONS = 30
    SUCCESS_ITERATIONS = 3
    STALL_ITERATIONS = 5

    def __init__(self, *args, **kwargs):
        super().__init__(WizardCheckType.UV_CALIBRATE_CENTER, *args, **kwargs)

    async def async_task_run(self, actions: UserActionBroker):
        hw = self._package.hw
        try:
            # NOTE: Fans and UV already started by previous check
            try:
                await self.calibrate()
            except UVCalibrationError:
                if self._result.boost or self._uv_meter.sixty_points:
                    raise
                # Possibly the UV sensor does not match UV LED wavelength, lets try with corrected readings
                self._result.boost = True
                self._logger.info(
                    "Requested intensity cannot be reached by max. allowed PWM,"
                    " run second iteration with boosted results on (PWM=%d)",
                    self.pwm,
                )
                await self.calibrate()

            boost_threshold = (self.factoryUvPwm / 100) * (100 + hw.config.uvCalibBoostTolerance)
            pwm_too_high = self.pwm > self.SECOND_PASS_THRESHOLD or self.pwm > boost_threshold
            if pwm_too_high and not self._result.boost and not self._uv_meter.sixty_points:
                self._result.boost = True
                self._logger.info(
                    "Boosted results applied due to bigger tolerance. Factory: %d, max: %f, tolerance: %d",
                    self.factoryUvPwm,
                    (self.factoryUvPwm / 100) * (100 + hw.config.uvCalibBoostTolerance),
                    hw.config.uvCalibBoostTolerance,
                )
                hw.beepAlarm(2)
                await self.calibrate()
        except (Exception, CancelledError):
            hw.uv_led.off()
            hw.stop_fans()
            raise

    async def calibrate(self):
        hw = self._package.hw
        # Start UV led with minimal pwm
        self.pwm = self._calibration_params.min_pwm

        error = 0
        integrated_error = 0
        success_count = 0
        stall_count = 0
        last_pwm = self.pwm
        data = None

        # Calibrate LED Power
        hw.start_fans()
        for iteration in range(0, self.TUNING_ITERATIONS):
            await sleep(0)
            hw.uv_led.pwm = round(self.pwm)
            # Read new intensity value
            data = self._uv_meter.read_data()
            if data is None:
                raise UVMeterCommunicationFailed()
            self.intensity = data.uvMean if not self._result.boost else data.uvMean * self.BOOST_MULTIPLIER
            self.deviation = data.uvStdDev
            data.uvFoundPwm = -1  # for debug log
            self._logger.info("New UV sensor data %s", str(data))

            # Calculate new error
            error = hw.config.uvCalibIntensity - self.intensity
            integrated_error += error

            self._logger.info(
                "UV pwm tuning: pwm: %d, intensity: %f, error: %f, integrated: %f, iteration: %d, success count: %d",
                self.pwm,
                self.intensity,
                error,
                integrated_error,
                iteration,
                success_count,
            )

            # Compute progress based on threshold / error ratio
            self.progress = 1 if error == 0 else min(1, self._calibration_params.intensity_error_threshold / abs(error))

            # Break cycle when error is tolerable
            if abs(error) < self._calibration_params.intensity_error_threshold:
                if success_count >= self.SUCCESS_ITERATIONS:
                    break
                success_count += 1
            else:
                success_count = 0

            # Adjust PWM according to error, integrated error and operational limits
            self.pwm = self.pwm + self._calibration_params.param_p * error + self.PARAM_I * integrated_error
            self.pwm = max(self._calibration_params.min_pwm, min(self._calibration_params.max_pwm, self.pwm))

            # Break cycle if calibration makes no progress
            if last_pwm == self.pwm:
                stall_count += 1
                if stall_count > self.STALL_ITERATIONS:
                    self._logger.warning("UV Calibration stall detected")
                    break
            else:
                last_pwm = self.pwm
                stall_count = 0

        # Report ranges and deviation errors
        if error > self._calibration_params.intensity_error_threshold:
            self._logger.error("UV intensity error: %f", error)
            raise UVTooDimm(
                self.intensity, hw.config.uvCalibIntensity - self._calibration_params.intensity_error_threshold
            )
        if error < -self._calibration_params.intensity_error_threshold:
            self._logger.error("UV intensity error: %f", error)
            raise UVTooBright(
                self.intensity, hw.config.uvCalibIntensity + self._calibration_params.intensity_error_threshold
            )
        if self.deviation > self.INTENSITY_DEVIATION_THRESHOLD:
            self._logger.error("UV deviation: %f", self.deviation)
            raise UVDeviationTooHigh(self.deviation, self.INTENSITY_DEVIATION_THRESHOLD)

        data.uvFoundPwm = hw.uv_led.pwm
        self._result.data = data


class UVCalibrateEdge(UVCalibrate):
    def __init__(self, *args, **kwargs):
        super().__init__(WizardCheckType.UV_CALIBRATE_EDGE, *args, **kwargs)

    async def async_task_run(self, actions: UserActionBroker):
        try:
            # NOTE: Fans and UV already started by previous check
            await self.calibrate()
        finally:
            self._package.hw.uv_led.off()
            # All the previous checks stop fans in case of exception as the fans are supposed to run for the whole
            # group of checks. This one is run the last so it is supposed to turn the fans off.
            self._package.hw.stop_fans()
            self._package.exposure_image.blank_screen()

    async def calibrate(self):
        hw = self._package.hw
        self._package.exposure_image.open_screen()
        max_pwm = self._calibration_params.max_pwm
        # check PWM value from previous step
        self.pwm = hw.uv_led.pwm
        data = None
        while self.pwm <= max_pwm:
            await sleep(0)
            hw.uv_led.pwm = self.pwm
            # Read new intensity value
            data = self._uv_meter.read_data()
            if data is None:
                raise UVMeterCommunicationFailed()

            self.min_value = data.uvMinValue if not self._result.boost else data.uvMinValue * self.BOOST_MULTIPLIER
            self.deviation = data.uvStdDev
            data.uvFoundPwm = -1  # for debug log
            self._logger.info("New UV sensor data %s", str(data))
            self._logger.info("UV pwm tuning: pwm: %d, minValue: %f", self.pwm, self.min_value)

            # Compute progress based on threshold / value ratio
            self.progress = min(1, self.min_value / hw.config.uvCalibMinIntEdge)

            # Break cycle when minimal intensity (on the edge) is ok
            if self.min_value >= hw.config.uvCalibMinIntEdge:
                break
            self.pwm += 1

        # Report ranges
        if self.pwm > max_pwm:
            self._logger.error("UV PWM %d > allowed PWM %d", self.pwm, max_pwm)
            raise UVTooDimm(self.pwm, max_pwm)
        if self.deviation > self.INTENSITY_DEVIATION_THRESHOLD:
            self._logger.error("UV deviation: %f", self.deviation)
            raise UVDeviationTooHigh(self.deviation, self.INTENSITY_DEVIATION_THRESHOLD)

        data.uvFoundPwm = hw.uv_led.pwm
        self._result.data = data

    def get_result_data(self) -> Dict[str, Any]:
        return asdict(self._result.data)


class UVRemoveCalibrator(Check):
    def __init__(self, uv_meter: UvLedMeterMulti):
        super().__init__(WizardCheckType.UV_METER_REMOVED)
        self._uv_meter = uv_meter

    async def async_task_run(self, actions: UserActionBroker):
        state = PushState(WizardState.UV_CALIBRATION_REMOVE_UV_METER)
        actions.push_state(state)
        self._logger.info("Waiting for user to remove UV calibrator")
        while self._uv_meter.present and not test_runtime.testing:
            self._logger.debug("UV meter still present")
            await sleep(1)
        self._logger.info("UV calibrator removed")
        actions.drop_state(state)


class UVCalibrateApply(Check):
    def __init__(
        self,
        package: WizardDataPackage,
        result: UVCalibrationResult,
        reset_display_counter: bool,
        reset_led_counter: bool,
    ):
        super().__init__(WizardCheckType.UV_CALIBRATION_APPLY_RESULTS)
        self._package = package
        self._result = result
        self._reset_led_counter = reset_led_counter
        self._reset_display_counter = reset_display_counter

    async def async_task_run(self, actions: UserActionBroker):
        result: Queue[bool] = Queue()

        def discard(loop: AbstractEventLoop):
            loop.call_soon_threadsafe(partial(result.put_nowait, False))

        def apply(loop: AbstractEventLoop):
            loop.call_soon_threadsafe(partial(result.put_nowait, True))

        actions.uv_discard_results.register_callback(partial(discard, get_running_loop()))
        actions.uv_apply_result.register_callback(partial(apply, get_running_loop()))
        state = PushState(WizardState.UV_CALIBRATION_APPLY_RESULTS)
        actions.push_state(state)
        self._logger.info("Waiting for result apply resolve")
        value = await result.get()
        actions.drop_state(state)
        if not value:
            self._logger.info("User decided not to apply result, canceling")
            raise CancelledError()
        self._logger.info("Applying results")
        await self.apply_results()

    def get_result_data(self) -> Dict[str, Any]:
        data = asdict(self._result.data)
        data["boost"] = self._result.boost
        return data

    async def apply_results(self):
        hw = self._package.hw
        # Save HW config
        previous_uv_pwm = hw.config.uvPwm
        # TODO: use config_writer instead
        hw.config.uvPwm = self._result.data.uvFoundPwm
        hw.uv_led.pwm = self._result.data.uvFoundPwm
        del hw.config.uvCurrent  # remove old value too
        hw.config.write()

        # Save factory HW config
        if self._package.runtime_config.factory_mode or not hw.config.data_factory_values["uvPwm"]:
            try:
                with FactoryMountedRW():
                    hw.config.write_factory()
            except Exception as exception:
                raise FailedToSaveFactoryConfig() from exception

        # Save counters log
        if self._reset_led_counter or self._reset_display_counter:
            stats = TomlConfigStats(defines.statsData, hw)
            stats.load()
            self._logger.info("stats: %s", stats)
            counters_data = {
                datetime.utcnow().isoformat(): {
                    "started_projects": stats["started_projects"],
                    "finished_projects": stats["finished_projects"],
                    "total_layers": stats["layers"],
                    "total_seconds": stats["total_seconds"],
                    "total_resin": stats["total_resin"],
                    "uvLed_seconds": hw.uv_led.usage_s,
                    "display_seconds": hw.exposure_screen.usage_s,
                    "factoryMode": self._package.runtime_config.factory_mode,
                    "resetDisplayCounter": self._reset_display_counter,
                    "resetUvLedCounter": self._reset_led_counter,
                    "previousUvPwm": previous_uv_pwm,
                    "newUvPwm": hw.config.uvPwm,
                }
            }
            self._logger.info("counter data: %s", counters_data)
            try:
                with FactoryMountedRW():
                    with defines.counterLog.open("a") as f:
                        toml.dump(counters_data, f)
            except Exception as exception:
                raise FailedToSaveFactoryConfig() from exception

            save_wizard_history(defines.counterLog)

        # Reset UV led counter in MC
        if self._reset_led_counter:
            hw.uv_led.clear_usage()

        # Reset Display counter in MC
        if self._reset_display_counter:
            hw.exposure_screen.clear_usage()
