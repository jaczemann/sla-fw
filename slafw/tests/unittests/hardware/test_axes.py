# This file is part of the SLA firmware
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2020-2024 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio
import unittest
from abc import ABC
from time import sleep
from typing import Tuple
from unittest import IsolatedAsyncioTestCase
from unittest.mock import Mock, PropertyMock, patch

from slafw import defines
from slafw.configs.hw import HwConfig
from slafw.configs.unit import Nm, Ustep, Unit
from slafw.errors.errors import TiltPositionFailed, TowerPositionFailed, \
    TowerMoveFailed, TiltMoveFailed, TowerHomeFailed, TiltHomeFailed
from slafw.hardware.axis import Axis, HomingStatus

from slafw.hardware.printer_model import PrinterModel
from slafw.hardware.sl1.tilt import TiltSL1
from slafw.hardware.sl1.tower import TowerSL1
from slafw.motion_controller.sl1_controller import MotionControllerSL1
from slafw.tests.base import SlafwTestCase
from slafw.exposure.profiles import ExposureProfileSL1


# pylint: disable = protected-access
# pylint: disable = too-many-public-methods


class DoNotRunTestDirectlyFromBaseClass:
    # pylint: disable = too-few-public-methods
    class BaseSL1AxisTest(SlafwTestCase, IsolatedAsyncioTestCase, ABC):
        axis: Axis  # reference to axis object (TiltSL1, TowerSL1)
        pos: Unit  # arbitrary position used for testing moves
        unit: Unit
        incompatible_unit: Unit
        fullstep_offset: Tuple[int]  # tower is set to 1/16 ustepping, tilt is set to 1/32

        def setUp(self) -> None:
            super().setUp()
            self.config = HwConfig()
            self.power_led = Mock()
            self.mcc = MotionControllerSL1()
            self.mcc.open()
            self.printer_model = PrinterModel.SL1

        def tearDown(self) -> None:
            self.mcc.exit()
            super().tearDown()

        def test_position(self):
            positions = [self.pos, self.pos // 2]
            for position in positions:
                self.axis.position = position
                self.assertEqual(position, self.axis.position)
            self.axis._move_api_max()
            with self.assertRaises((TiltPositionFailed, TowerPositionFailed)):
                self.axis.position = position

        def test_basic_movement(self):
            self.assertFalse(self.axis.moving)
            self.axis.move(self.pos)
            self.assertTrue(self.axis.moving)
            while self.axis.moving:
                self.assertFalse(self.axis.on_target_position)
                sleep(0.1)
            self.assertFalse(self.axis.moving)
            self.assertTrue(self.axis.on_target_position)
            self.assertEqual(self.axis.position, self.pos)

        def test_ensure_position_async(self):
            path = "slafw.hardware.sl1." + self.axis.name + "." + self.axis.name.capitalize() + "SL1.position"
            pos = self.pos
            one = self.unit(1)
            two = self.unit(2)
            side_effect_position = [one, one, one, two, two, two, pos, pos]

            # normal behaviour
            self.axis.position = self.axis.home_position
            self.axis.move(pos)
            asyncio.run(self.axis.ensure_position_async())
            self.assertFalse(self.axis.moving)
            self.assertEqual(self.axis.position, pos)

            # successful retries 2
            self.axis.position = self.axis.home_position
            with patch(path, new_callable=PropertyMock) as mock_position:
                mock_position.side_effect = side_effect_position
                self.axis.move(pos)
                asyncio.run(self.axis.ensure_position_async(retries=2))
                self.assertFalse(self.axis.moving)
            self.assertEqual(self.axis.position, pos)

            # maximum tries reached
            self.axis.position = self.axis.home_position
            with patch(path, new_callable=PropertyMock) as mock_position:
                mock_position.side_effect = side_effect_position
                self.axis.move(pos)
                with self.assertRaises((TowerMoveFailed, TiltMoveFailed)):
                    asyncio.run(self.axis.ensure_position_async(retries=1))
                self.assertFalse(self.axis.moving)

        def test_move_ensure(self):
            self.axis.position = self.axis.home_position
            self.axis.move_ensure(self.pos)
            self.assertFalse(self.axis.moving)
            self.assertEqual(self.axis.position, self.pos)

        def test_move_api_stop(self):
            self.axis.position = self.pos
            self.axis.move_api(2)
            self.assertTrue(self.axis.moving)
            actual_profile = self.axis.actual_profile
            self.axis.move_api(0)
            self.assertFalse(self.axis.moving)
            self.assertLess(self.pos, self.axis.position)
            self.assertEqual(actual_profile, self.axis.actual_profile)

        def _test_move_api_up_down(self, speed: int):
            # set some profile which is not used for moving axis
            self.axis.actual_profile = self.axis.profiles[10]
            actual_profile = self.axis.actual_profile
            self.axis.position = self.pos
            self.axis.move_api(speed)
            self.assertTrue(self.axis.moving)
            self.assertLess(self.pos, self.axis.position)
            # check that profile has changed from the initial
            self.assertNotEqual(actual_profile, self.axis.actual_profile)
            actual_profile = self.axis.actual_profile
            self.axis.stop()
            self.axis.position = self.pos
            self.axis.move_api(-speed)
            self.assertTrue(self.axis.moving)
            self.assertGreater(self.pos, self.axis.position)
            self.assertEqual(actual_profile, self.axis.actual_profile)

        def test_move_api_slow_up_down(self):
            self._test_move_api_up_down(1)

        def test_move_api_fast_up_down(self):
            self._test_move_api_up_down(2)

        # TODO: fix mc-fw to mimic real HW accurately. Now moves tilt: +31 -32 steps, tower +-16 steps
        def test_move_api_goto_fullstep(self):
            for i in range(2):
                self.axis.position = self.pos
                # move down fast (-2)
                # move up fast (2)
                self.axis.move_api(((i - 1) * 4) + 2)
                self.assertTrue(self.axis.moving)
                self.axis.stop()
                pos = self.axis.position
                self.axis.move_api(0, fullstep=True)
                self.assertEqual(pos + self.fullstep_offset[i],
                                 self.axis.position)

        def stop(self) -> None:
            self.axis.position = self.axis.home_position
            self.axis.move(self.pos)
            while self.axis.moving:
                self.axis.stop()
                self.assertFalse(self.axis.moving)
                self.assertGreater(0, self.axis.position)

        def test_release(self):
            self.axis.sync_ensure()
            self.axis.position = self.axis.home_position
            self.axis.move_api(2)
            self.axis.release()
            self.assertFalse(self.axis.synced)

        # TODO: fix mc-fw to mimic real HW accurately. Now moves tilt: +31 -32 steps, tower +-16 steps
        def test_go_to_fullstep(self):
            for i in range(2):
                self.axis.position = self.pos
                self.axis.go_to_fullstep(go_up=bool(i))
                self.assertEqual(self.axis.position,
                                 self.pos + self.fullstep_offset[i])

        def _assert_homing_status_reached(self, status: HomingStatus, timeout_s = 60):
            for _ in range(timeout_s * 10):
                if self.axis.homing_status == status:
                    break
                sleep(0.1)
            self.assertEqual(status, self.axis.homing_status)

        def test_sync(self):
            self.axis.position = self.pos
            self.assertEqual(HomingStatus.UNKNOWN, self.axis.homing_status)
            self.axis.sync()
            self.assertLess(HomingStatus.SYNCED.value, self.axis.homing_status.value)
            self._assert_homing_status_reached(HomingStatus.SYNCED)
            self.assertTrue(self.axis.synced)
            self.axis.release()
            self.assertFalse(self.axis.synced)
            self.assertEqual(HomingStatus.UNKNOWN, self.axis.homing_status)

        def test_sync_ensure(self):
            self.axis.sync_ensure()
            self.assertEqual(HomingStatus.SYNCED, self.axis.homing_status)

        def test_sync_wait_async(self):
            path = "slafw.hardware.sl1." + self.axis.name + "." + self.axis.name.capitalize() + "SL1.homing_status"
            # successful rehome
            with patch(path, new_callable=PropertyMock) as mock_status:
                mock_status.side_effect = [HomingStatus.BLOCKED_AXIS, HomingStatus.BLOCKED_AXIS, HomingStatus.SYNCED]
                asyncio.run(self.axis.sync_ensure_async(retries=2))
                self.assertFalse(self.axis.moving)
            self.assertTrue(self.axis.synced)

            # maximum tries reached
            with patch(path, new_callable=PropertyMock) as mock_status:
                mock_status.side_effect = [HomingStatus.BLOCKED_AXIS, HomingStatus.BLOCKED_AXIS, HomingStatus.SYNCED]
                with self.assertRaises((TiltHomeFailed, TowerHomeFailed)):
                    asyncio.run(self.axis.sync_ensure_async(retries=1))
                self.assertFalse(self.axis.moving)


        def test_home_calibrate_wait(self):
            self.assertEqual(HomingStatus.UNKNOWN, self.axis.homing_status)
            self.axis.home_calibrate_wait()
            self.assertEqual(HomingStatus.SYNCED, self.axis.homing_status)
            # TODO: improve mc-code to test the result of calibration

        async def test_verify_async_unknown(self) -> None:
            self.assertEqual(HomingStatus.UNKNOWN, self.axis.homing_status)
            task = asyncio.create_task(self.axis.verify_async())
            self.assertLess(self.axis.homing_status.value, HomingStatus.SYNCED.value)
            await task
            self.assertEqual(self.axis.config_height_position, self.axis.position)

        async def test_verify_async_already_synced(self) -> None:
            await self.axis.sync_ensure_async()
            self.assertEqual(HomingStatus.SYNCED, self.axis.homing_status)
            task = self.axis.verify_async()
            self.assertEqual(HomingStatus.SYNCED, self.axis.homing_status)
            await task
            self.assertEqual(self.axis.config_height_position, self.axis.position)
            # already home axis does not home. Just move to top position

        def test_actual_profile(self):
            for profile in self.axis.profiles:
                self.axis.actual_profile = profile
                self.assertEqual(profile, self.axis.actual_profile)

        def test_unit(self):
            self.assertEqual(type(self.axis.position), self.unit)
            self.assertEqual(type(self.axis.home_position), self.unit)
            self.assertEqual(type(self.axis.config_height_position), self.unit)
            self.axis.position = self.unit(0)
            with self.assertRaises(TypeError):
                self.axis.position = self.incompatible_unit(0)
            self.axis.move(self.unit(0))
            with self.assertRaises(TypeError):
                self.axis.move(self.incompatible_unit(0))

        def test_set_sensitivity(self):
            self.axis.set_stepper_sensitivity(-2)
            p = self.axis.profiles.homingFast
            p.get_values()["starting_steprate"].set_factory_value(p, 10)
            with self.assertRaises(RuntimeError):
                self.axis.set_stepper_sensitivity(0)


class TestTilt(DoNotRunTestDirectlyFromBaseClass.BaseSL1AxisTest):

    def setUp(self):
        super().setUp()
        tower = TowerSL1(self.mcc, self.config, self.power_led, self.printer_model)
        self.axis = TiltSL1(self.mcc, self.config, self.power_led, tower, self.printer_model)
        self.exposure_profile = ExposureProfileSL1(factory_file_path=self.SAMPLES_DIR / "fast_default_exposure_profile.json")
        self.pos = self.axis.config_height_position / 4 # aprox 1000 usteps
        self.unit = Ustep
        self.incompatible_unit = Nm
        self.fullstep_offset = (Ustep(-32), Ustep(31))
        self.axis.start()

    def test_name(self) -> str:
        self.assertEqual(self.axis.name, "tilt")

    def test_home_position(self) -> int:
        self.assertEqual(self.axis.home_position, Ustep(0))

    def test_config_height_position(self) -> int:
        self.assertEqual(self.axis.config_height_position, self.config.tiltHeight)

    def test_raise_move_failed(self):
        with self.assertRaises(TiltMoveFailed):
            self.axis._raise_move_failed()

    def test_raise_home_failed(self):
        with self.assertRaises(TiltHomeFailed):
            self.axis._raise_home_failed()

    def test_move_api_min(self) -> None:
        self.axis.position = self.pos
        self.axis._move_api_min()
        self.assertTrue(self.axis.moving)
        self.assertEqual(self.axis._target_position, self.axis.home_position)

    def test_move_api_max(self) -> None:
        self.axis._move_api_max()
        self.assertTrue(self.axis.moving)
        self.assertEqual(self.axis._target_position, self.config.tiltMax)

    def test_move_api_get_profile(self):
        self.assertEqual(self.axis._move_api_get_profile(1), self.axis.profiles.homingSlow)
        self.assertEqual(self.axis._move_api_get_profile(2), self.axis.profiles.homingFast)

    def test_sensitivity(self):
        self.assertEqual(self.axis.sensitivity, self.config.tiltSensitivity)

    # TODO: test better
    def test_layer_up(self):
        self.axis.layer_up_wait(self.exposure_profile.below_area_fill)
        self.assertAlmostEqual(self.axis.config_height_position, self.axis.position)

    # TODO test better
    def test_layer_down(self):
        asyncio.run(self.axis.layer_down_wait_async(self.exposure_profile.below_area_fill))
        self.assertLessEqual(abs(self.axis.position),
                             Ustep(defines.tiltHomingTolerance))

    def test_stir_resin(self):
        asyncio.run(self.axis.stir_resin_async(self.exposure_profile.below_area_fill))
        self.assertEqual(self.axis.position, self.config.tiltHeight)


class TestTower(DoNotRunTestDirectlyFromBaseClass.BaseSL1AxisTest):

    def setUp(self):
        super().setUp()
        self.axis = TowerSL1(self.mcc, self.config, self.power_led, self.printer_model)
        self.pos = self.axis.home_position / 2
        self.unit = Nm
        self.incompatible_unit = Ustep
        offset = self.config.tower_microsteps_to_nm(16)
        self.fullstep_offset = (-offset, offset)
        self.axis.start()

    def test_name(self):
        self.assertEqual(self.axis.name, "tower")

    def test_home_position(self):
        self.assertEqual(self.axis.home_position, self.config.tower_height_nm)

    def test_config_height_position(self):
        print(type(self.axis.home_position))
        print(type(self.config.tower_height_nm))
        print(self.axis.home_position)
        print(self.config.tower_height_nm)
        self.assertEqual(self.axis.home_position, self.config.tower_height_nm)

    def test_raise_move_failed(self):
        with self.assertRaises(TowerMoveFailed):
            self.axis._raise_move_failed()

    def test_raise_home_failed(self):
        with self.assertRaises(TowerHomeFailed):
            self.axis._raise_home_failed()

    def test_move_api_min(self) -> None:
        self.axis._move_api_min()
        self.assertTrue(self.axis.moving)
        self.assertEqual(self.axis._target_position, self.config.calib_tower_offset_nm)

    def test_move_api_max(self) -> None:
        self.axis.position = self.pos
        self.axis._move_api_max()
        self.assertTrue(self.axis.moving)
        self.assertEqual(self.axis._target_position, self.config.tower_height_nm)

    def test_move_api_get_profile(self):
        self.assertEqual(self.axis._move_api_get_profile(1), self.axis.profiles.homingSlow)
        self.assertEqual(self.axis._move_api_get_profile(2), self.axis.profiles.homingFast)

    def test_sensitivity(self):
        self.assertEqual(self.axis.sensitivity, self.config.tiltSensitivity)

if __name__ == "__main__":
    unittest.main()
