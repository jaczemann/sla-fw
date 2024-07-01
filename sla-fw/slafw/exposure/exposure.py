# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2020-2024 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

# TODO: Fix following pylint problems
# pylint: disable=too-many-lines
# pylint: disable=too-many-locals
# pylint: disable=too-many-branches
# pylint: disable=too-many-statements
# pylint: disable=too-many-instance-attributes
# pylint: disable=too-many-public-methods


from __future__ import annotations

import asyncio
import logging
import weakref
from pathlib import Path
from abc import abstractmethod
from asyncio import CancelledError, Task
from datetime import datetime, timedelta, timezone
from hashlib import md5
from queue import Queue, Empty
from threading import Thread, Event, Lock
from time import sleep, monotonic_ns
from typing import Optional, Any, List, Dict
from weakref import WeakMethod
from dataclasses import dataclass, field, asdict

import psutil
from PySignal import Signal

from slafw import defines, test_runtime
from slafw.api.devices import HardwareDeviceId
from slafw.configs.unit import Nm
from slafw.configs.stats import TomlConfigStats
from slafw.errors import tests
from slafw.errors.errors import (
    TiltHomeFailed,
    TiltFailed,
    TowerFailed,
    TowerMoveFailed,
    ResinMeasureFailed,
    ResinTooLow,
    ResinTooHigh,
    WarningEscalation,
    NotAvailableInState,
    ExposureCheckDisabled,
    ExposureError,
    FanFailed,
)
from slafw.errors.warnings import AmbientTooHot, AmbientTooCold, ResinNotEnough, PrinterWarning, ExpectOverheating
from slafw.functions.files import remove_files
from slafw.hardware.power_led_action import WarningAction, ErrorAction
from slafw.project.functions import check_ready_to_print
from slafw.project.project import Project
from slafw.states.exposure import ExposureState, ExposureCheck, ExposureCheckResult
from slafw.exposure.traceable_collections import TraceableDict
from slafw.exposure.profiles import SingleLayerProfileSL1
from slafw.wizard.data_package import WizardDataPackage


class ExposureCheckRunner:
    def __init__(self, check: ExposureCheck, expo: Exposure):
        self.logger = logging.getLogger(__name__)
        self.check_type = check
        self.expo: Exposure = weakref.proxy(expo)
        self.warnings: List[PrinterWarning] = []

    async def start(self):
        self.logger.info("Running: %s", self.check_type)
        self.expo.data.check_results[self.check_type] = ExposureCheckResult.RUNNING
        try:
            await self.run()
            if self.warnings:
                self.logger.warning("Check warnings: %s", self.warnings)
                self.expo.data.check_results[self.check_type] = ExposureCheckResult.WARNING
            else:
                self.logger.info("Success: %s", self.check_type)
                self.expo.data.check_results[self.check_type] = ExposureCheckResult.SUCCESS
        except ExposureCheckDisabled:
            self.logger.info("Disabled: %s", self.check_type)
            self.expo.data.check_results[self.check_type] = ExposureCheckResult.DISABLED
        except Exception:
            self.logger.exception("Exception: %s", self.check_type)
            self.expo.data.check_results[self.check_type] = ExposureCheckResult.FAILURE
            raise

    def raise_warning(self, warning):
        self.warnings.append(warning)
        self.expo.raise_preprint_warning(warning)

    @abstractmethod
    async def run(self):
        ...


class TempsCheck(ExposureCheckRunner):
    def __init__(self, *args, **kwargs):
        super().__init__(ExposureCheck.TEMPERATURE, *args, **kwargs)

    async def run(self):
        if test_runtime.injected_preprint_warning:
            self.raise_warning(test_runtime.injected_preprint_warning)

        # Try reading UV temp, this raises exceptions if something goes wrong
        _ = self.expo.hw.uv_led_temp.value

        ambient = self.expo.hw.ambient_temp
        if ambient.value < ambient.min:
            self.raise_warning(AmbientTooCold(ambient.value))
        elif ambient.value > ambient.max:
            self.raise_warning(AmbientTooHot(ambient.value))


class CoverCheck(ExposureCheckRunner):
    def __init__(self, *args, **kwargs):
        super().__init__(ExposureCheck.COVER, *args, **kwargs)

    async def run(self):
        if not self.expo.hw.config.coverCheck:
            self.logger.info("Disabling cover check")
            raise ExposureCheckDisabled()

        self.logger.info("Waiting for user to close the cover")
        with self.expo.pending_warning:
            while True:
                if self.expo.hw.isCoverClosed():
                    self.expo.state = ExposureState.CHECKS
                    self.logger.info("Cover closed")
                    return

                self.expo.state = ExposureState.COVER_OPEN
                await asyncio.sleep(0.1)


class ProjectDataCheck(ExposureCheckRunner):
    def __init__(self, *args, **kwargs):
        super().__init__(ExposureCheck.PROJECT, *args, **kwargs)

    async def run(self):
        await asyncio.sleep(0)
        if Path(self.expo.project.data.path).parent != defines.previousPrints:
            self.logger.debug("Running disk cleanup")
            remove_files(self.logger, list(defines.previousPrints.glob("*")))
        await asyncio.sleep(0)
        self.logger.debug("Running project copy and check")
        self.expo.project.copy_and_check()
        self.logger.info("Project after copy and check: %s", str(self.expo.project))
        await asyncio.sleep(0)
        self.logger.debug("Initiating project in ExposureImage")
        self.expo.startProject()
        await asyncio.sleep(0)
        # show all warnings
        if self.expo.project.warnings:
            for warning in self.expo.project.warnings:
                self.raise_warning(warning)
        await asyncio.sleep(0)


class FansCheck(ExposureCheckRunner):
    def __init__(self, *args, **kwargs):
        super().__init__(ExposureCheck.FAN, *args, **kwargs)

    async def run(self):
        # Warm-up fans
        self.logger.info("Warming up fans")

        fans = {
            (self.expo.hw.uv_led_fan, HardwareDeviceId.UV_LED_FAN.value),
            (self.expo.hw.blower_fan, HardwareDeviceId.BLOWER_FAN.value),
            (self.expo.hw.rear_fan, HardwareDeviceId.REAR_FAN.value),
        }

        for fan, fan_id in fans:
            fan.auto_control = False

        self.expo.hw.start_fans()
        if not test_runtime.testing:
            self.logger.debug("Waiting %.2f secs for fans", defines.fanStartStopTime)
            await asyncio.sleep(defines.fanStartStopTime)
        else:
            self.logger.debug("Not waiting for fans to start due to testing")

        # Check fans
        self.logger.info("Checking fan errors")
        self.expo.hw.mcc.get_fans_error(check_for_updates=True)

        if not defines.fan_check_override:
            for fan, fan_id in fans:
                if fan.error:
                    self.expo.data.check_results[ExposureCheck.FAN] = ExposureCheckResult.FAILURE
                    raise FanFailed(fan_id)

        self.expo.hw.uv_led_fan.auto_control = True

        self.logger.info("Fans OK")

class ResinCheck(ExposureCheckRunner):
    RETRIES = 2

    def __init__(self, *args, **kwargs):
        super().__init__(ExposureCheck.RESIN, *args, **kwargs)

    async def measure_resin_retries(self, retries: int) -> float:
        try:
            return await self.do_measure_resin()
        except (ResinMeasureFailed, ResinTooLow, ResinTooHigh):
            if retries:
                return await self.measure_resin_retries(retries - 1)
            raise

    async def do_measure_resin(self) -> float:
        volume_ml = await self.expo.hw.get_resin_volume_async()
        self.expo.setResinVolume(volume_ml)

        try:
            if not volume_ml:
                raise ResinMeasureFailed(volume_ml)

            if volume_ml < defines.resinMinVolume:
                raise ResinTooLow(volume_ml, defines.resinMinVolume)

            if volume_ml > defines.resinMaxVolume:
                raise ResinTooHigh(volume_ml)
        except ResinMeasureFailed:
            await self.expo.hw.tower.move_ensure_async(self.expo.hw.tower.resin_start_pos_nm)
            raise
        return volume_ml

    async def run(self):
        if not self.expo.hw.config.resinSensor:
            raise ExposureCheckDisabled()

        volume_ml = await self.measure_resin_retries(self.RETRIES)

        required_volume_ml = self.expo.project.used_material + defines.resinMinVolume
        self.logger.debug(
            "min: %d [ml], requested: %d [ml], measured: %d [ml]", defines.resinMinVolume, required_volume_ml, volume_ml
        )

        # User is already informed about required refill during print if project has volume over 100 %
        if volume_ml < required_volume_ml <= defines.resinMaxVolume:
            self.logger.info("Raising resin not enough warning")
            self.raise_warning(ResinNotEnough(volume_ml, required_volume_ml))


class StartPositionsCheck(ExposureCheckRunner):
    def __init__(self, *args, **kwargs):
        super().__init__(ExposureCheck.START_POSITIONS, *args, **kwargs)

    async def run(self):
        # tilt is handled by StirringCheck

        self.logger.info("Tower to print start position")
        self.expo.hw.tower.actual_profile = self.expo.hw.tower.profiles.homingFast
        try:
            # TODO: Constant in code, seems important
            await self.expo.hw.tower.move_ensure_async(Nm(0.25 * 1_000_000), retries=2)
            self.logger.debug("Tower on print start position")
        except TowerMoveFailed as e:
            exception = e
            self.expo.exception = exception
            self.expo.hw.tower.actual_profile = self.expo.hw.tower.profiles.homingFast
            await self.expo.hw.tower.move_ensure_async(self.expo.hw.config.tower_height_nm)
            raise TowerMoveFailed from exception
        await self.expo.hw.tilt.wait_to_stop_async()
        self.logger.debug("Tilt on print start position")


class StirringCheck(ExposureCheckRunner):
    def __init__(self, *args, **kwargs):
        super().__init__(ExposureCheck.STIRRING, *args, **kwargs)

    async def run(self):
        if not self.expo.actual_layer_profile.use_tilt:
            raise ExposureCheckDisabled()
        await self.expo.hw.tilt.stir_resin_async(self.expo.actual_layer_profile)


@dataclass
class ExposureData:
    changed: Signal
    instance_id: int
    state: ExposureState = ExposureState.INIT
    actual_layer: int = 0
    resin_count_ml: float = 0.0
    resin_remain_ml: Optional[float] = None
    resin_warn: bool = False
    resin_low: bool = False
    remaining_wait_sec: int = 0
    estimated_total_time_ms: int = -1
    print_start_time: datetime = datetime.now(tz=timezone.utc)
    print_end_time: datetime = datetime.fromtimestamp(0, tz=timezone.utc)
    exposure_end: Optional[datetime] = None
    check_results: TraceableDict = field(default_factory=TraceableDict)
    warning: Optional[Warning] = None  # Current preprint warning
    fatal_error: Optional[Exception] = None
    current_area_fill: int = 0

    def __setattr__(self, key: str, value: Any):
        object.__setattr__(self, key, value)
        self.changed.emit(key, value)

def _exposure_data_filter(data):
    return dict(x for x in data if isinstance(x[1], (int, float, datetime, ExposureState)))


class Exposure:
    def __init__(self, job_id: int, package: WizardDataPackage, changed_signal: Optional[Signal] = None):
        self.logger = logging.getLogger(__name__)
        self.project: Optional[Project] = None
        self.hw = package.hw
        self.exposure_image = package.exposure_image
        self.data = ExposureData(changed = changed_signal if changed_signal else Signal(), instance_id = job_id)
        self.resin_volume = None
        self.tower_position_nm = self.hw.tower.minimal_position
        self.slow_layers_done = 0
        self.warning_occurred = Signal()  # Generic warning has been issued
        self.canceled = False
        self.commands: Queue[str] = Queue()  # pylint: disable=unsubscriptable-object
        self.warning_dismissed = Event()
        self.warning_result: Optional[Exception] = None
        self.pending_warning = Lock()
        weak_run = WeakMethod(self.run)
        self._thread = Thread(target=lambda: weak_run()())  # pylint: disable = unnecessary-lambda
        self._large_fill_remain_nm: int = 0
        self.hw.uv_led_fan.error_changed.connect(self._on_uv_led_fan_error)
        self.hw.blower_fan.error_changed.connect(self._on_blower_fan_error)
        self.hw.rear_fan.error_changed.connect(self._on_rear_fan_error)
        self._checks_task: Optional[Task] = None
        self.actual_layer_profile: SingleLayerProfileSL1 = None
        # this not working in ExposureData
        self.data.check_results.changed.connect(self._on_check_result_change)

    def _on_check_result_change(self):
        self.data.changed.emit("check_results", self.data.check_results)

    def read_project(self, project_file: str):
        self.state = ExposureState.READING_DATA
        check_ready_to_print(self.hw.config, self.hw.uv_led.parameters)
        try:
            # read project
            self.project = Project(
                    self.hw,
                    project_file,
                    self.data.changed)
            self.data.estimated_total_time_ms = self.estimate_total_time_ms()
            self.state = ExposureState.CONFIRM
            # recompute estimetad time after project times change
            self.project.times_changed.connect(self._on_times_changed)
        except ExposureError as exception:
            self.logger.exception("Exposure read_project exception")
            self.state = ExposureState.FAILURE
            self.data.fatal_error = exception
            self.hw.uv_led.off()
            self.hw.stop_fans()
            self.hw.motors_release()
            raise
        self.logger.info("Readed project '%s'", project_file)

    def _on_times_changed(self):
        self.data.estimated_total_time_ms = self.estimate_total_time_ms()

    def confirm_print_start(self):
        self._thread.start()
        self.commands.put("pour_resin_in")

    def confirm_resin_in(self):
        self.commands.put("checks")

    def confirm_print_warning(self):
        self.logger.info("User confirmed print check warnings")
        self.warning_dismissed.set()

    def reject_print_warning(self):
        self.logger.info("User rejected print due to warnings")
        self.warning_result = WarningEscalation(self.data.warning)
        self.warning_dismissed.set()

    def cancel(self):
        self.canceled = True
        if self.in_progress:
            # Will be terminated by after layer finished
            if self.state == ExposureState.CHECKS and self._checks_task:
                self.logger.info("Canceling preprint checks")
                self._checks_task.cancel()
            self.logger.info("Canceling exposure")
            if self.state != ExposureState.FAILURE:
                self.state = ExposureState.PENDING_ACTION
            self.doExitPrint()
        else:
            # Exposure thread not yet running (cancel before start)
            self.logger.info("Canceling not started exposure")
            self.state = ExposureState.DONE

    def try_cancel(self):
        self.logger.info("Trying cancel exposure")
        cancelable_states = ExposureState.cancelable_states()
        if self.state in cancelable_states:
            self.cancel()
        else:
            raise NotAvailableInState(self.state, cancelable_states)
        return True

    def startProject(self):
        self.data.actual_layer = 0
        self.data.resin_count_ml = 0.0
        self.slow_layers_done = 0
        self.exposure_image.new_project(self.project)
        self.actual_layer_profile = self.project.exposure_profile.above_area_fill

    def prepare(self):
        self.exposure_image.preload_image(0)
        # set tower for the first layer, tilt should be leveled
        self.hw.tower.actual_profile = self.hw.tower.profiles[self.actual_layer_profile.tower_profile]
        self.tower_position_nm = Nm(self.project.layers[0].height_nm) + self.hw.config.calib_tower_offset_nm
        self.hw.tower.move_ensure(self.tower_position_nm)

        self.exposure_image.blank_screen()
        self.hw.uv_led.pwm = self.hw.config.uvPwmPrint
        self.hw.exposure_screen.start_counting_usage()

    @property
    def in_progress(self):
        if not self._thread:
            return False

        return self._thread.is_alive()

    @property
    def done(self):
        return self.state in ExposureState.finished_states()

    @property
    def progress(self) -> float:
        if self.state == ExposureState.FINISHED:
            return 1

        completed_layers = self.data.actual_layer - 1 if self.data.actual_layer else 0
        return completed_layers / self.project.total_layers

    @property
    def state(self) -> ExposureState:
        return self.data.state

    @state.setter
    def state(self, state: ExposureState):
        self.logger.info("State changed: %s -> %s", self.data.state, state)
        self.data.state = state

    def waitDone(self):
        if self._thread:
            self._thread.join()

    def doUpAndDown(self):
        self.state = ExposureState.PENDING_ACTION
        self.commands.put("updown")

    def doExitPrint(self):
        self.commands.put("exit")

    def doFeedMe(self):
        self.state = ExposureState.PENDING_ACTION
        self.commands.put("feedme")

    def doPause(self):
        self.commands.put("pause")

    def doContinue(self):
        self.commands.put("continue")

    def doBack(self):
        self.commands.put("back")

    def setResinVolume(self, volume):
        if volume is None:
            self.resin_volume = None
        else:
            self.resin_volume = volume + int(self.data.resin_count_ml)
            self.data.resin_remain_ml = volume

    def estimate_total_time_ms(self):
        if self.project:
            return self.project.count_remain_time(0, 0)
        self.logger.warning("No active project to get estimated print time")
        return -1

    def estimate_remain_time_ms(self) -> int:
        if self.project:
            return self.project.count_remain_time(self.data.actual_layer, self.slow_layers_done)
        self.logger.warning("No active project to get remaining time")
        return -1

    def expected_finish_timestamp(self) -> float:
        """
        Get timestamp of expected print end

        :return: Timestamp as float
        """
        end = datetime.now(tz=timezone.utc) + timedelta(milliseconds=self.estimate_remain_time_ms())
        return end.timestamp()

    def stats_seen(self):
        self.state = ExposureState.DONE

    def _exposure_simple(self, times_ms):
        uv_on_remain_ms = times_ms[0]
        self.hw.uv_led.pulse(uv_on_remain_ms)
        while uv_on_remain_ms > 0:
            sleep(uv_on_remain_ms / 1100.0)
            uv_on_remain_ms = self.hw.uv_led.pulse_remaining
        self.exposure_image.blank_screen()

    def _exposure_calibration(self, times_ms):
        end = monotonic_ns()
        ends = []
        for time_ms in times_ms:
            end += time_ms * 1e6
            ends.append(end)
        i = 0
        last = len(ends) - 1
        self.logger.debug("uv on")
        self.hw.uv_led.on()
        for end in ends:
            diff = 0
            while diff >= 0:
                sleep(diff / 1e9 / 1.1)
                diff = end - monotonic_ns()
            self.exposure_image.blank_area(i, i == last)
            i += 1
            if abs(diff) > 1e7:
                self.logger.warning("Exposure end delayed %f ms", abs(diff) / 1e6)
        self.hw.uv_led.off()

    def _do_frame(self, times_ms, was_stirring, layer_height_nm, last_layer):
        white_pixels = self.exposure_image.sync_preloader()
        self.exposure_image.screenshot_rename()

        delay_before = int(self.actual_layer_profile.delay_before_exposure_ms)
        if delay_before:
            self.logger.info("Delay before exposure [s]: %f", delay_before / 1000)
            sleep(delay_before / 1000)

        delay_stirring = int(self.hw.config.stirring_delay_ms)
        if was_stirring and delay_stirring:
            self.logger.info("Stirring delay [s]: %f", delay_stirring / 1000)
            sleep(delay_stirring / 1000)

        self.exposure_image.blit_image()

        exp_time_ms = sum(times_ms)
        self.data.exposure_end = datetime.now(tz=timezone.utc) + timedelta(seconds=exp_time_ms / 1e3)
        self.logger.info("Exposure started: %d ms, end: %s", exp_time_ms, self.data.exposure_end)

        if len(times_ms) == 1:
            self._exposure_simple(times_ms)
        else:
            self._exposure_calibration(times_ms)

        self.logger.info("Exposure done")
        self.exposure_image.preload_image(self.data.actual_layer + 1)

        delay_after = int(self.actual_layer_profile.delay_after_exposure_ms)
        if delay_after:
            self.logger.info("Delay after exposure [s]: %f", delay_after / 1000)
            sleep(delay_after / 1000)

        self.data.current_area_fill = white_pixels / self.hw.exposure_screen.parameters.pixels_per_percent
        large_fill = self.data.current_area_fill > self.project.exposure_profile.area_fill
        self.logger.debug("large_fill:%s (current: %d, threshold: %d)",
                large_fill, self.data.current_area_fill, self.project.exposure_profile.area_fill)

        # Force large fill by height
        if large_fill:
            self._large_fill_remain_nm = self.hw.config.forceSlowTiltHeight
        elif self._large_fill_remain_nm > 0:
            self._large_fill_remain_nm -= layer_height_nm
            large_fill = True
            self.logger.debug("large_fill forced by height, remain[nm]: %d", self._large_fill_remain_nm)

        # Force large fill on first layers
        if self.data.actual_layer < self.project.first_slow_layers:
            self.logger.debug("large_fill forced by first layers, %d/%d",
                    self.data.actual_layer + 1, self.project.first_slow_layers)
            large_fill = True

        if large_fill:
            self.slow_layers_done += 1
            self.actual_layer_profile = self.project.exposure_profile.above_area_fill
        else:
            self.actual_layer_profile = self.project.exposure_profile.below_area_fill

        try:
            self.hw.tilt.layer_peel_moves(self.actual_layer_profile, self.tower_position_nm, last_layer)
        except TiltHomeFailed:
            return False, white_pixels

        return True, white_pixels

    def upAndDown(self):
        with WarningAction(self.hw.power_led):
            if self.hw.config.up_and_down_uv_on:
                self.hw.uv_led.on()

            self.state = ExposureState.GOING_UP
            self.hw.tower.actual_profile = self.hw.tower.profiles.homingFast
            self.hw.tower.move_ensure(self.hw.config.tower_height_nm)

            self.state = ExposureState.WAITING
            for sec in range(self.hw.config.up_and_down_wait):
                cnt = self.hw.config.up_and_down_wait - sec
                self.data.remaining_wait_sec = cnt
                sleep(1)
                if self.hw.config.coverCheck and not self.hw.isCoverClosed():
                    self.state = ExposureState.COVER_OPEN
                    while not self.hw.isCoverClosed():
                        sleep(1)
                    self.state = ExposureState.WAITING

            if self.actual_layer_profile.use_tilt:
                self.state = ExposureState.STIRRING
                self.hw.tilt.stir_resin(self.actual_layer_profile)

            self.state = ExposureState.GOING_DOWN
            position_nm = self.hw.config.up_and_down_z_offset_nm
            position_nm = max(position_nm, 0)
            self.hw.tower.move_ensure(position_nm)
            self.hw.tower.actual_profile = self.hw.tower.profiles.layer22

            self.state = ExposureState.PRINTING

    def doWait(self, beep=False):
        command = None
        break_free = {"exit", "back", "continue"}
        while not command:
            if beep:
                self.hw.beepAlarm(3)
            sleep(1)

            try:
                command = self.commands.get_nowait()
            except Empty:
                command = None
            except Exception:
                self.logger.exception("getCommand exception")
                command = None

            if command in break_free:
                break

        return command

    def _wait_uv_cool_down(self) -> Optional[str]:
        if not self.hw.uv_led_temp.overheat:
            return None

        self.logger.error("UV LED overheat - waiting for cooldown")
        state = self.state
        self.state = ExposureState.COOLING_DOWN
        with ErrorAction(self.hw.power_led):
            while True:
                try:
                    if self.commands.get_nowait() == "exit":
                        return "exit"
                except Empty:
                    pass
                if not self.hw.uv_led_temp.overheat:
                    break
                self.hw.beepAlarm(3)
                sleep(3)
            self.state = state
            return None

    def doStuckRelease(self):
        self.state = ExposureState.STUCK

        with WarningAction(self.hw.power_led):
            self.hw.tilt.release()
            if self.doWait(True) == "back":
                raise TiltFailed()

            self.state = ExposureState.STUCK_RECOVERY
            self.hw.tilt.sync_ensure()
            self.state = ExposureState.STIRRING
            self.hw.tilt.stir_resin(self.actual_layer_profile)

        self.state = ExposureState.PRINTING

    def run(self):
        try:
            self.logger.info("Started exposure thread")
            self.logger.info("Motion controller tilt profiles: %s", self.hw.tilt.profiles)
            self.logger.info("Exposure profiles: %s", self.project.exposure_profile)

            while not self.done:
                command = self.commands.get()
                if command == "exit":
                    self.hw.check_cover_override = False
                    self.logger.info("Exiting exposure thread on exit command")
                    if self.canceled:
                        self.state = ExposureState.CANCELED
                    break

                if command == "pour_resin_in":
                    with WarningAction(self.hw.power_led):
                        self.hw.check_cover_override = True
                        asyncio.run(self._home_axis())
                        self.state = ExposureState.POUR_IN_RESIN
                        continue

                if command == "checks":
                    self.hw.check_cover_override = False
                    asyncio.run(self._run_checks())
                    self.run_exposure()
                    continue

                self.logger.error('Undefined command: "%s" ignored', command)

            self.logger.info("Exiting exposure thread on state: %s", self.state)

        except CancelledError:
            self.state = ExposureState.CANCELED
            self.logger.exception("Exposure thread canceled.")
        except WarningEscalation as e:
            self.state = ExposureState.CANCELED
            self.logger.exception("Exposure thread canceled due to WarningEscalation.")
            self.data.fatal_error = e
        except Exception as e:
            self.state = ExposureState.FAILURE
            self.logger.exception("Exposure thread failed.")
            self.data.fatal_error = e
        finally:
            try:
                # Rise the tower if you can -> current exception is not related to tower or tilt function
                if self.data.fatal_error not in (None, TiltFailed, TowerFailed, TiltHomeFailed, TowerMoveFailed):
                    self._final_go_up()
            except Exception as e:
                self.logger.exception("Exposure thread final go up failed.")
                if self.data.fatal_error is None:
                    self.data.fatal_error = e
        if self.project:
            self.project.data_close()
        self._print_end_hw_off()
        self.logger.info("Exposure thread finished")

    def raise_preprint_warning(self, warning: Warning):
        self.logger.warning("Warning being raised in pre-print: %s", type(warning))
        with self.pending_warning:
            self.warning_result = None
            self.data.warning = warning
            old_state = self.state
            self.state = ExposureState.CHECK_WARNING
            self.warning_dismissed.clear()
            self.logger.debug("Waiting for warning resolution")
            self.warning_dismissed.wait()
            self.logger.debug("Warnings resolved")
            self.data.warning = None
            self.state = old_state
            if self.warning_result:
                raise self.warning_result  # pylint: disable = raising-bad-type

    async def _home_axis(self):
        if not self.hw.tower.synced or not self.hw.tilt.synced:
            self.state = ExposureState.HOMING_AXIS
            self.logger.info("Homing axis to pour resin")
            await asyncio.gather(self.hw.tower.verify_async(), self.hw.tilt.verify_async())

    async def _run_checks(self):
        self._checks_task = asyncio.create_task(self._run_checks_task())
        await self._checks_task

    async def _run_checks_task(self):
        self.state = ExposureState.CHECKS
        self.logger.info("Running pre-print checks")
        for check in ExposureCheck:
            self.data.check_results.update({check: ExposureCheckResult.SCHEDULED})

        with WarningAction(self.hw.power_led):
            await asyncio.gather(FansCheck(self).start(), TempsCheck(self).start(), ProjectDataCheck(self).start())
            await CoverCheck(self).start()
            await ResinCheck(self).start()
            await StartPositionsCheck(self).start()
            await StirringCheck(self).start()

    def run_exposure(self):
        # TODO: Where is this supposed to be called from?
        self.prepare()

        self.logger.info("Running exposure")
        self.state = ExposureState.PRINTING
        self.data.print_start_time = datetime.now(tz=timezone.utc)
        statistics = TomlConfigStats(defines.statsData, self.hw)
        statistics.load()
        statistics["started_projects"] += 1
        statistics.save_raw()
        seconds = 0

        project = self.project
        project_hash = md5(project.name.encode()).hexdigest()[:8] + "_"
        was_stirring = True
        exposure_compensation = 0

        with WarningAction(self.hw.power_led):
            while self.data.actual_layer < project.total_layers:
                try:
                    command = self.commands.get_nowait()
                except Empty:
                    command = None
                except Exception:
                    self.logger.exception("getCommand exception")
                    command = None

                if command == "updown":
                    self.upAndDown()
                    was_stirring = True
                    exposure_compensation = self.hw.config.upAndDownExpoComp * 100

                if command == "exit":
                    break

                if command == "inject_tower_fail":
                    self.logger.error("Injecting fatal tower fail")
                    raise TowerFailed()

                if command == "pause":
                    if self.doWait(False) == "exit":
                        break

                if self._wait_uv_cool_down() == "exit":
                    break

                if self.resin_volume:
                    self._update_resin()

                if command == "feedme" or self.data.resin_low:
                    with ErrorAction(self.hw.power_led):
                        self.state = ExposureState.FEED_ME
                        sub_command = self.doWait(self.data.resin_low)

                        if sub_command == "continue":
                            # update resin volume
                            self.setResinVolume(defines.resinMaxVolume)

                        # Force user to close the cover
                        self._wait_cover_close()

                        # Stir resin before resuming print
                        if self.actual_layer_profile.use_tilt:
                            self.state = ExposureState.STIRRING
                            self.hw.tilt.stir_resin(self.actual_layer_profile)
                        was_stirring = True

                    # Resume print
                    self.state = ExposureState.PRINTING

                if (
                    self.hw.config.up_and_down_every_layer
                    and self.data.actual_layer
                    and not self.data.actual_layer % self.hw.config.up_and_down_every_layer
                ):
                    self.doUpAndDown()
                    was_stirring = True
                    exposure_compensation = self.hw.config.upAndDownExpoComp * 100

                layer = project.layers[self.data.actual_layer]

                self.logger.info(
                    "Layer started » {"
                    " 'layer': '%04d/%04d (%s)',"
                    " 'exposure [ms]': %s,"
                    " 'slow_layers_done': %d,"
                    " 'height [mm]': '%.3f/%.3f',"
                    " 'elapsed [min]': %d,"
                    " 'remain [ms]': %d,"
                    " 'used [ml]': %.2f,"
                    " 'remaining [ml]': %.2f,"
                    " 'RAM': '%.1f%%',"
                    " 'CPU': '%.1f%%'"
                    " }",
                    self.data.actual_layer + 1,
                    project.total_layers,
                    layer.image.replace(project.name, project_hash),
                    str(layer.times_ms),
                    self.slow_layers_done,
                    int(self.tower_position_nm - self.hw.config.calib_tower_offset_nm) / 1e6,
                    project.total_height_nm / 1e6,
                    int(round((datetime.now(tz=timezone.utc) - self.data.print_start_time).total_seconds() / 60)),
                    self.estimate_remain_time_ms(),
                    self.data.resin_count_ml,
                    self.data.resin_remain_ml if self.data.resin_remain_ml else -1,
                    psutil.virtual_memory().percent,
                    psutil.cpu_percent(),
                )

                times_ms = list(layer.times_ms)
                times_ms[0] += exposure_compensation
                last_layer = self.data.actual_layer + 1 == project.total_layers

                # _do_frame() will move tower to NEXT layer
                if not last_layer:
                    self.tower_position_nm += Nm(project.layers[self.data.actual_layer + 1].height_nm)

                success, white_pixels = self._do_frame(times_ms, was_stirring, layer.height_nm, last_layer)
                if not success:
                    with ErrorAction(self.hw.power_led):
                        self.doStuckRelease()

                was_stirring = False
                exposure_compensation = 0

                # /1e21 (1e7 ** 3) - we want cm3 (=ml) not nm3
                self.data.resin_count_ml += (
                    white_pixels * self.hw.exposure_screen.parameters.pixel_size_nm ** 2 * layer.height_nm / 1e21
                )
                self.logger.debug("resin_count_ml: %f", self.data.resin_count_ml)

                seconds = (datetime.now(tz=timezone.utc) - self.data.print_start_time).total_seconds()
                self.data.actual_layer += 1

        if self.canceled:
            self.hw.tilt.layer_down_wait(self.actual_layer_profile)

        self._final_go_up()

        is_finished = not self.canceled
        if is_finished:
            statistics["finished_projects"] += 1
        statistics["layers"] += self.data.actual_layer
        statistics["total_seconds"] += seconds
        statistics["total_resin"] += self.data.resin_count_ml
        statistics.save_raw()
        exposure_times = (
            f"{project.exposure_time_first_ms:d}/{project.exposure_time_ms:d}/{project.calibrate_time_ms:d} s"
        )
        self.logger.info(
            "Job finished » { 'job': %d, 'project': '%s', 'finished': %s, "
            "'autoOff': %s, 'Layers': '%d/%d', 'printTime [s]': %d, "
            "'used [ml]': %.2f, 'remaining [ml]': %.2f, 'exposure [s]': '%s', 'height [mm]': %g, }",
            statistics["started_projects"],
            project_hash[:-1],
            is_finished,
            self.hw.config.autoOff,
            self.data.actual_layer,
            project.total_layers,
            seconds,
            self.data.resin_count_ml,
            self.data.resin_remain_ml if self.data.resin_remain_ml else -1,
            exposure_times,
            int(self.tower_position_nm - self.hw.config.calib_tower_offset_nm) / 1e6,
        )
        self.exposure_image.save_display_usage()
        self._print_end_hw_off()
        self.state = ExposureState.CANCELED if self.canceled else ExposureState.FINISHED
        self.logger.debug("Exposure ended")

    def _update_resin(self):
        self.data.resin_remain_ml = self.resin_volume - self.data.resin_count_ml
        self.data.resin_warn = self.data.resin_remain_ml < defines.resinLowWarn
        self.data.resin_low = self.data.resin_remain_ml < defines.resinFeedWait

    def _wait_cover_close(self) -> bool:
        """
        Waits for cover close

        :return: True if was waiting false otherwise
        """
        if not self.hw.config.coverCheck:
            return False

        if self.hw.isCoverClosed():
            self.logger.info("Cover already closed skipping close wait")
            return False

        self.logger.info("Waiting for user to close the cover")
        old_state = self.state
        while not self.hw.isCoverClosed():
            self.state = ExposureState.COVER_OPEN
            sleep(0.1)
        self.state = old_state
        self.logger.info("Cover closed now")
        return True

    def _final_go_up(self):
        previous_state = self.state  # Store previous state to revert to it when done.
        self.state = ExposureState.GOING_UP
        self.hw.motors_stop()
        self.hw.tower.actual_profile = self.hw.tower.profiles.homingFast
        self.hw.tower.move_ensure(self.hw.config.tower_height_nm)
        self.state = previous_state

    def _print_end_hw_off(self):
        self.hw.uv_led.off()
        self.hw.stop_fans()
        self.hw.motors_release()
        self.hw.exposure_screen.stop_counting_usage()
        self.hw.uv_led.save_usage()
        # TODO: Save also display statistics once we have display component
        self.data.print_end_time = datetime.now(tz=timezone.utc)

    def _on_uv_led_fan_error(self, error: bool):
        if error:
            self.warning_occurred.emit(ExpectOverheating(failed_fans_text="UV LED"))

    def _on_blower_fan_error(self, error: bool):
        if error:
            self.warning_occurred.emit(ExpectOverheating(failed_fans_text="Blower"))

    def _on_rear_fan_error(self, error: bool):
        if error:
            self.warning_occurred.emit(ExpectOverheating(failed_fans_text="Rear"))

    def inject_fatal_error(self):
        self.logger.info("Scheduling exception inject")
        self.commands.put("inject_tower_fail")

    def inject_exception(self, code: str):
        exception = tests.get_instance_by_code(code)
        self.logger.info("Injecting exception %s", exception)
        self.warning_occurred.emit(exception)

    @property
    def persistent_data(self) -> Dict[str, Any]:
        return asdict(self.data, dict_factory=_exposure_data_filter)

    @persistent_data.setter
    def persistent_data(self, data: Dict[str, Any]):
        self.data = ExposureData(changed = self.data.changed, **data)
