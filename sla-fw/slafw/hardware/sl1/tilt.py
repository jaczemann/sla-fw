# This file is part of the SLA firmware
# Copyright (C) 2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio
from time import sleep
from pathlib import Path
from typing import List

from slafw import defines
from slafw.configs.hw import HwConfig
from slafw.configs.unit import Ustep, Nm
from slafw.errors.errors import TiltPositionFailed
from slafw.hardware.printer_model import PrinterModel
from slafw.hardware.axis import HomingStatus
from slafw.hardware.power_led import PowerLed
from slafw.hardware.sl1.tower import TowerSL1
from slafw.hardware.sl1.axis import AxisSL1
from slafw.hardware.sl1.tilt_profiles import MovingProfilesTiltSL1, TILT_CFG_LOCAL
from slafw.hardware.tilt import Tilt
from slafw.motion_controller.sl1_controller import MotionControllerSL1
from slafw.exposure.profiles import SingleLayerProfileSL1


class TiltSL1(Tilt, AxisSL1):
    # pylint: disable=too-many-instance-attributes
    # pylint: disable=too-many-public-methods
    # pylint: disable=too-many-arguments

    def __init__(self, mcc: MotionControllerSL1, config: HwConfig,
                 power_led: PowerLed, tower: TowerSL1, printer_model: PrinterModel):
        super().__init__(config, power_led)
        self._mcc = mcc
        self._tower = tower
        default_profiles = Path(defines.dataPath) / printer_model.name / f"default_{self.name}_moving_profiles.json" # type: ignore[attr-defined]
        self._profiles = MovingProfilesTiltSL1(factory_file_path=TILT_CFG_LOCAL, default_file_path=default_profiles)
        self._profiles.apply_profile = self.apply_profile
        self._sensitivity = {
            #                -2       -1        0        +1       +2
            "homingFast": [[20, 5], [20, 6], [20, 7], [21, 9], [22, 12]],
            "homingSlow": [[16, 3], [16, 5], [16, 7], [16, 9], [16, 11]],
        }

    def start(self):
        self.apply_all_profiles()
        self.actual_profile = self._profiles.homingFast    # type: ignore

    def apply_all_profiles(self):
        try:
            self.set_stepper_sensitivity(self.sensitivity)
        except RuntimeError as e:
            self._logger.error("%s - ignored", e)
        self._profiles.apply_all()

    @property
    def position(self) -> Ustep:
        return Ustep(self._mcc.doGetInt("?tipo"))

    @position.setter
    def position(self, position: Ustep) -> None:
        self._check_units(position, Ustep)
        if self.moving:
            raise TiltPositionFailed("Failed to set tilt position since its moving")
        self._mcc.do("!tipo", int(position))
        self._target_position = position
        self._logger.debug("Position set to: %d ustep", self._target_position)

    @property
    def moving(self):
        if self._mcc.doGetInt("?mot") & 2:
            return True
        return False

    def move(self, position):
        self._check_units(position, Ustep)
        self._mcc.do("!tima", int(position))
        self._target_position = position
        self._logger.debug("Move initiated. Target position: %d ustep",
                           self._target_position)

    def stop(self):
        axis_moving = self._mcc.doGetInt("?mot")
        self._mcc.do("!mot", axis_moving & ~2)
        self._target_position = self.position
        self._logger.debug("Move stopped. Rewriting target position to: %d ustep",
                           self._target_position)

    def go_to_fullstep(self, go_up: bool):
        self._mcc.do("!tigf", int(go_up))

    async def layer_down_wait_async(self, layer_profile: SingleLayerProfileSL1) -> None:
        # initial release movement with optional sleep at the end
        self.actual_profile = self._profiles[layer_profile.tilt_down_initial_profile]
        if layer_profile.tilt_down_offset_steps > Ustep(0):
            self.move(self.position - layer_profile.tilt_down_offset_steps)
            await self.wait_to_stop_async()
        await asyncio.sleep(int(layer_profile.tilt_down_offset_delay_ms) / 1000)
        # next movement may be splited
        self.actual_profile = self._profiles[layer_profile.tilt_down_finish_profile]
        movePerCycle = self.position // layer_profile.tilt_down_cycles
        for _ in range(layer_profile.tilt_down_cycles):
            self.move(self.position - movePerCycle)
            await self.wait_to_stop_async()
            await asyncio.sleep(int(layer_profile.tilt_down_delay_ms) / 1000)
        tolerance = Ustep(defines.tiltHomingTolerance)
        # if not already in endstop ensure we end up at defined bottom position
        if not self._mcc.checkState("endstop"):
            self.move(-tolerance)
            # tilt will stop moving on endstop OR by stallguard
            await self.wait_to_stop_async()
        # check if tilt is on endstop and within tolerance
        if self._mcc.checkState("endstop") and -tolerance <= self.position <= tolerance:
            return
        # unstuck
        self._logger.warning("Tilt unstucking")
        self.actual_profile = self._profiles.layer400   # type: ignore
        count = Ustep(0)
        step = Ustep(128)
        while count < self._config.tiltMax and not self._mcc.checkState("endstop"):
            self.position = step
            self.move(self.home_position)
            await self.wait_to_stop_async()
            count += step
        await self.sync_ensure_async(retries=0)

    async def layer_up_wait_async(self, layer_profile: SingleLayerProfileSL1, tilt_height: Ustep=Ustep(0)) -> None:
        if tilt_height == self.home_position: # use self._config.tiltHeight by default
            _tilt_height = self.config_height_position
        else: # in case of calibration there is need to force new unstored tilt height
            _tilt_height = tilt_height

        self.actual_profile = self._profiles[layer_profile.tilt_up_initial_profile]
        self.move(_tilt_height - layer_profile.tilt_up_offset_steps)
        await self.wait_to_stop_async()
        await asyncio.sleep(int(layer_profile.tilt_up_offset_delay_ms) / 1000)
        self.actual_profile = self._profiles[layer_profile.tilt_up_finish_profile]

        # finish move may be also splited in multiple sections
        movePerCycle = (_tilt_height - self.position) // layer_profile.tilt_up_cycles
        for _ in range(layer_profile.tilt_up_cycles):
            self.move(self.position + movePerCycle)
            await self.wait_to_stop_async()
            await asyncio.sleep(int(layer_profile.tilt_up_delay_ms) / 1000)

    def release(self) -> None:
        axis_enabled = self._mcc.doGetInt("?ena")
        self._mcc.do("!ena", axis_enabled & ~2)

    async def stir_resin_async(self, layer_profile: SingleLayerProfileSL1) -> None:
        for _ in range(self._config.stirring_moves):
            await self.layer_down_wait_async(layer_profile)
            await self.layer_up_wait_async(layer_profile)

    @property
    def homing_status(self) -> HomingStatus:
        return HomingStatus(self._mcc.doGetInt("?tiho"))

    def sync(self) -> None:
        self._mcc.do("!tiho")
        sleep(0.2)  #FIXME: mc-fw does not start the movement immediately -> wait a bit

    async def home_calibrate_wait_async(self):
        self._mcc.do("!tihc")
        await super().home_calibrate_wait_async()
        self.position = self.home_position

    async def verify_async(self) -> None:
        if not self.synced:
            await self._tower.wait_to_stop_async()
            await self.sync_ensure_async()
        self.actual_profile = self._profiles.move8000   # type: ignore
        await self.move_ensure_async(self._config.tiltHeight)

    @property
    def profiles(self) -> MovingProfilesTiltSL1:
        return self._profiles

    def _read_profile_id(self) -> int:
        return self._mcc.doGetInt("?tics")

    def _read_profile_data(self) -> List[int]:
        return self._mcc.doGetIntList("?ticf")

    def _write_profile_id(self, profile_id: int):
        self._mcc.do("!tics", profile_id)

    def _write_profile_data(self):
        self._mcc.do("!ticf", *self._actual_profile.dump())

    async def layer_peel_moves_async(self, layer_profile: SingleLayerProfileSL1, position_nm: Nm, last_layer: bool) -> None:
        self._tower.actual_profile = self._tower.profiles[layer_profile.tower_profile]
        if layer_profile.use_tilt:
            await self.layer_down_wait_async(layer_profile)
            if layer_profile.tower_hop_height_nm:
                await self._tower.move_ensure_async(position_nm + layer_profile.tower_hop_height_nm)
                if not last_layer:
                    await self.layer_up_wait_async(layer_profile)
                    await self._tower.move_ensure_async(position_nm)
            elif not last_layer:
                await self._tower.move_ensure_async(position_nm)
                await self.layer_up_wait_async(layer_profile)
        else:
            await self._tower.move_ensure_async(position_nm + layer_profile.tower_hop_height_nm)
            if not last_layer:
                await self._tower.move_ensure_async(position_nm)
