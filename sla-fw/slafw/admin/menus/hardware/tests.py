# This file is part of the SLA firmware
# Copyright (C) 2021-2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later
from functools import partial
from pathlib import Path
from threading import Thread
from time import sleep, monotonic
from typing import Callable

from slafw import defines
from slafw.admin.control import AdminControl
from slafw.admin.items import AdminAction, AdminTextValue, AdminLabel
from slafw.admin.menu import AdminMenu
from slafw.admin.menus.dialogs import Error, Confirm, Info, Wait
from slafw.configs.unit import Ustep, Nm, Ms
from slafw.exposure.profiles import EXPOSURE_PROFILES_DEFAULT_NAME, ExposureProfileSL1
from slafw.hardware.axis import Axis
from slafw.hardware.profiles import SingleProfile
from slafw.libPrinter import Printer
from slafw.libUvLedMeterMulti import UvLedMeterMulti
from slafw.errors.errors import TiltHomeFailed, TowerHomeFailed, TiltMoveFailed, TowerMoveFailed
from slafw.hardware.power_led_action import WarningAction
from slafw.image.cairo import draw_chess


class HardwareTestMenu(AdminMenu):
    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control)
        self._printer = printer

        self.add_back()
        self.add_items(
            (
                AdminAction("Resin sensor test", self.resin_sensor_test, "refill_color"),
                AdminAction("Infinite UV calibrator test", self.infinite_uv_calibrator_test, "uv_calibration"),
                AdminAction("Infinite complex test", self.infinite_test, "restart"),
                AdminAction("Touchscreen test", self._control.touchscreen_test, "touchscreen-icon"),
                AdminAction("Axis timing test", self.axis_timing_test, "exposure_times_color"),
                AdminAction(
                    "Exposure timing test (print speeds)",
                    lambda: self.enter(ExposureProfilesMenu(self._control, printer)),
                    "uv_calibration"
                ),
            )
        )

    def resin_sensor_test(self):
        self._control.enter(
            Confirm(
                self._control,
                self.do_resin_sensor_test,
                text="Is there the correct amount of resin in the tank?\n"
                    "Is the tank secured with both screws?",
            )
        )

    def do_resin_sensor_test(self):
        self.enter(ResinSensorTestMenu(self._control, self._printer))

    def infinite_uv_calibrator_test(self):
        self.enter(InfiniteUVCalibratorMenu(self._control))

    def infinite_test(self):
        self._control.enter(
            Confirm(
                self._control,
                self.do_infinite_test,
                text="It is strongly recommended to NOT run this test.\n"
                    "This is an infinite routine which tests durability\n"
                    "of exposition display and mechanical parts.",
            )
        )

    def do_infinite_test(self):
        self._printer.hw.uv_led.save_usage()
        self.enter(InfiniteTestMenu(self._control, self._printer))

    def axis_timing_test(self):
        self.enter(AxisTimingTest(self._control, self._printer))

class InfiniteUVCalibratorMenu(AdminMenu):
    # pylint: disable = too-many-instance-attributes
    def __init__(self, control: AdminControl):
        super().__init__(control)

        self.add_items(
            (
                AdminTextValue.from_property(self, InfiniteUVCalibratorMenu.status, "sandclock_color"),
                AdminTextValue.from_property(self, InfiniteUVCalibratorMenu.value, "info_off_small_white"),
                AdminTextValue.from_property(self, InfiniteUVCalibratorMenu.iteration, "info_off_small_white"),
                AdminAction("Stop", self.stop, "cancel_color"),
            )
        )

        self._status = "Initializing"
        self._iteration = ""
        self._value = ""
        self._run = True
        self._thread = Thread(target=self._runner)
        self._thread.start()

    def on_leave(self):
        self._run = False
        self._thread.join()

    def stop(self):
        self.status = "Waiting for test thread to join"
        self.on_leave()
        self._control.pop()

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value: str):
        self._status = value

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value: str):
        self._value = value

    @property
    def iteration(self):
        return self._iteration

    @iteration.setter
    def iteration(self, value: str):
        self._iteration = value

    def _runner(self):
        self.status = "Connecting to UV calibrator"
        uvmeter = UvLedMeterMulti()
        connected = False

        cnt = 0
        while self._run:
            self.iteration = f"Successful reads: {cnt}"
            if connected:
                self.status = "Reading UV calibrator data"
                self.logger.info("Reading UV calibrator data")
                if uvmeter.read():
                    uv_mean = uvmeter.get_data().uvMean
                    self.logger.info("Red data: UVMean: %s", uv_mean)
                    self.value = f"Last uvMean = {uv_mean}"
                    cnt += 1
                else:
                    self.status = "UV calibrator disconnected"
                    self.logger.info("UV calibrator disconnected")
                    connected = False
            elif uvmeter.connect():
                self.status = "UV calibrator connected"
                self.logger.info("UV calibrator connected")
                connected = True
        self.status = "Closing UV calibrator"
        self.logger.info("Closing UV calibrator")
        uvmeter.close()


class ResinSensorTestMenu(AdminMenu):
    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control)

        self._printer = printer
        self._status = "Initializing"
        self.add_item(AdminTextValue.from_property(self, ResinSensorTestMenu.status, "sandclock_color"))
        self._thread = Thread(target=self._runner)
        self._thread.start()

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value: str):
        self._status = value

    def _runner(self):
        # TODO: vyzadovat zavreny kryt po celou dobu!
        with WarningAction(self._printer.hw.power_led):
            self.status = "Moving platform to the top..."

            try:
                self._printer.hw.tower.sync_ensure()
            except TowerHomeFailed:
                self._control.enter(Error(self._control, text="Failed to sync tower"))
                self._printer.hw.motors_release()
                return

            self.status = "Homing tilt..."
            try:
                self._printer.hw.tilt.sync_ensure()
            except TiltHomeFailed:
                self._control.enter(Error(self._control, text="Failed to sync tilt"))
                self._printer.hw.motors_release()
                return

            self._printer.hw.tilt.actual_profile = self._printer.hw.tilt.profiles.move8000
            self._printer.hw.tilt.move_ensure(self._printer.hw.config.tiltHeight)

            self.status = "Measuring...\nDo NOT TOUCH the printer"
            volume = round(self._printer.hw.get_precise_resin_volume_ml())

        if not volume:
            self._control.enter(Error(self._control, text="Measurement failed"))
            return

        self._control.enter(Info(self._control, f"Measured resin volume: {volume} ml", pop=2))


class InfiniteTestMenu(AdminMenu):
    # pylint: disable = too-many-instance-attributes
    # pylint: disable = too-many-statements
    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control)

        self.add_items(
            (
                AdminTextValue.from_property(self, InfiniteTestMenu.status, "sandclock_color"),
                AdminTextValue.from_property(self, InfiniteTestMenu.tower, "info_off_small_white"),
                AdminTextValue.from_property(self, InfiniteTestMenu.tilt, "info_off_small_white"),
                AdminAction("Stop", self.stop, "cancel_color"),
            )
        )
        self._printer = printer
        self._tower_cycles = 0
        self._tilt_cycles = 0
        self._run = True
        self._thread_tilt = Thread(target=self._runner_tilt)
        self._thread_tower = Thread(target=self._runner_tower)
        self._thread_init = Thread(target=self._runner_init)
        self._thread_init.start()

    def on_leave(self):
        self._run = False
        self._thread_tilt.join()
        self._thread_tower.join()

    def stop(self):
        self.status = "Waiting for test thread to join"
        self.on_leave()
        self._control.pop()

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value: str):
        self._status = value

    @property
    def tower(self):
        return f"Tower cycles: {self._tower_cycles}"

    @tower.setter
    def tower(self, value: int):
        self._tower_cycles = value

    @property
    def tilt(self):
        return f"Tilt cycles: {self._tilt_cycles}"

    @tilt.setter
    def tilt(self, value: int):
        self._tilt_cycles = value

    def _runner_init(self):
        self.status = "Initializing"
        self._printer.hw.exposure_screen.draw_pattern(draw_chess, 16)
        self._printer.hw.start_fans()
        self._printer.hw.uv_led.pwm = self._printer.hw.config.uvPwm
        self._printer.hw.uv_led.on()
        self._printer.hw.tower.sync_ensure()
        self._printer.hw.tilt.sync_ensure()
        self._printer.hw.tower.actual_profile = self._printer.hw.tower.profiles.homingFast
        self._printer.hw.tilt.actual_profile = self._printer.hw.tilt.profiles.homingFast

        self.status = "Running"
        self._thread_tilt.start()
        self._thread_tower.start()

    def _runner_tower(self):
        tower_cycles = 0
        with WarningAction(self._printer.hw.power_led):
            while self._run:
                self._printer.hw.tower.move_ensure(self._printer.hw.tower.resin_end_pos_nm)
                self._printer.hw.tower.sync_ensure()
                tower_cycles += 1
                self.tower = tower_cycles
            self._printer.hw_all_off()

    def _runner_tilt(self):
        tilt_cycles = 0
        with WarningAction(self._printer.hw.power_led):
            while self._run:
                self._printer.hw.tilt.move(self._printer.hw.tilt.config_height_position)
                self._printer.hw.tilt.wait_to_stop()
                self._printer.hw.tilt.move(Ustep(50))
                self._printer.hw.tilt.wait_to_stop()
                tilt_cycles += 1
                self.tilt = tilt_cycles
            self._printer.hw_all_off()


class AxisTimingTest(AdminMenu):
    # pylint: disable = too-many-instance-attributes
    # pylint: disable = too-many-statements
    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control)

        self.add_back()
        for profile in printer.hw.tilt.profiles:
            self.add_item(
                AdminAction(
                    "Tilt " + profile.name,
                    partial(self.test_axis, printer.hw.tilt, Ustep, profile),
                    "tank_reset_color"
                )
            )
        for profile in printer.hw.tower.profiles:
            self.add_item(
                AdminAction(
                    "Tower " + profile.name,
                    partial(self.test_axis, printer.hw.tower, Nm, profile),
                    "tower_offset_color"
                )
            )
        self._printer = printer

    def test_axis(self, axis: Axis, unit: Callable, profile: SingleProfile):
        # home both axis first
        self._printer.hw.tower.sync_ensure()
        self._printer.hw.tilt.sync_ensure()

        if axis.name == "tower":
            distances = (50_000, 100_000, 1_000_000, 2_000_000, 5_000_000,
                         10_000_000, 20_000_000)

        else:
            distances = (50, 100, 200, 500, 1000, 2000, 5000)

        # move axis to safe start position
        start_distance = unit(distances[0])
        axis.move(start_distance)
        axis.wait_to_stop()

        times: dict[str, dict]  = {}
        axis.actual_profile = profile
        times[profile.name] = {}
        for distance in distances:
            times[profile.name][str(distance)] = []
            for _ in range(5):
                try:
                    start_time = monotonic()
                    axis.move_ensure(unit(distance) + start_distance, 0)
                    stop_time = monotonic()
                    times[profile.name][str(distance)].append(stop_time - start_time)
                except (TiltMoveFailed, TowerMoveFailed) as e:
                    self.logger.warning("move failed, retrying. %s", e)
                    axis.move_ensure(unit(distance) + start_distance, 3)
                try:
                    start_time = monotonic()
                    axis.move_ensure(start_distance, 0)
                    stop_time = monotonic()
                    times[profile.name][str(distance)].append(stop_time - start_time)
                except (TiltMoveFailed, TowerMoveFailed) as e:
                    self.logger.warning("move failed, retrying. %s", e)
                    axis.move_ensure(start_distance, 3)
        self._printer.hw.tower.sync_ensure()
        self._printer.hw.motors_release()
        self.logger.info("%s profile %s", axis.name, profile.name)
        for tt in times.values():
            for distance, t in tt.items():
                if axis.name == "tower":
                    distance_nm = self._printer.hw.config.nm_to_tower_microsteps(unit(int(distance)))
                self.logger.info(
                    "%s, %f, %f, %f, %f, %s",
                    distance_nm,
                    sum(t) / len(t),
                    min(t),
                    max(t),
                    sum((x - (sum(t) / len(t))) ** 2 for x in t) / len(t),
                    t
                )


class ExposureProfilesMenu(AdminMenu):
    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control)
        self._printer = printer
        self.profiles = {}
        self.names = {}

        for speed in ("fast", "slow", "high_viscosity"):
            file_name = speed + EXPOSURE_PROFILES_DEFAULT_NAME
            exposure_profiles_path = (
                Path(defines.dataPath)
                / printer.hw.printer_model.name
                / file_name
            )  # type: ignore[attr-defined]
            self.profiles[speed] = ExposureProfileSL1(
                default_file_path=exposure_profiles_path)
            name = speed.replace("_", " ").capitalize() + " profile"
            self.names[speed] = name
        self.add_back()
        self.add_items((
            AdminAction(
                self.names["fast"],
                lambda: self.enter(Wait(self._control, self._test_fast_profile)),
                "uv_calibration"
            ),
            AdminAction(
                self.names["slow"],
                lambda: self.enter(Wait(self._control, self._test_slow_profile)),
                "uv_calibration"
            ),
            AdminAction(
                self.names["high_viscosity"],
                lambda: self.enter(Wait(self._control, self._test_hv_profile)),
                "uv_calibration"
            )
        ))

    def _test_fast_profile(self, status: AdminLabel):
        self._test_exposure_profile(status, self.profiles["fast"], self.names["fast"])

    def _test_slow_profile(self, status: AdminLabel):
        self._test_exposure_profile(status, self.profiles["slow"], self.names["slow"])

    def _test_hv_profile(self, status: AdminLabel):
        self._test_exposure_profile(status, self.profiles["high_viscosity"], self.names["high_viscosity"])

    def _test_exposure_profile(self, status: AdminLabel, profile: ExposureProfileSL1, name: str):
        hw = self._printer.hw
        status.set(f"{name} - Preparing axes")
        hw.tower.sync_ensure()
        hw.tilt.sync_ensure()

        tower_position = Nm(100_000_000)  # safe position for Z top
        hw.tower.actual_profile = hw.tower.profiles.moveFast
        hw.tower.move(tower_position)
        hw.tilt.actual_profile = hw.tilt.profiles.move8000
        hw.tilt.move(hw.tilt.config_height_position)
        hw.tilt.wait_to_stop()
        hw.tower.wait_to_stop()

        measure_moves = hw.config.measuringMoves
        for layer_profile in (profile.below_area_fill, profile.above_area_fill):
            run_time = 0.0
            for i in range(measure_moves):
                status.set(f"{name} - Move {i}/{measure_moves}")
                sleep(0)
                start_time = monotonic()
                hw.tilt.layer_peel_moves(layer_profile, tower_position + Nm(50000), last_layer=False)
                run_time += monotonic() - start_time
                sleep(0)
                hw.tower.move_ensure(tower_position)
                self.logger.debug("%s moves %d/%d, time mean: %d",
                                   layer_profile.name, i + 1, measure_moves, run_time * 1000 / (i + 1))
            moves_time_ms = Ms(run_time * 1000 / measure_moves)
            self.logger.info("Moves time for profile %d ms", moves_time_ms)
            self.logger.info("Calculated move times %d ms", hw.layer_peel_move_time(50000, layer_profile))
        hw.motors_release()
