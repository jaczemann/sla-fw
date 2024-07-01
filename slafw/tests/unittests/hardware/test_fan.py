# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio
import logging
from abc import ABC, abstractmethod
from asyncio import CancelledError
from functools import cached_property, wraps
from threading import Thread, Event, Lock
from typing import Optional
from unittest.mock import Mock

from slafw.configs.hw import HwConfig
from slafw.configs.writer import ConfigWriter
from slafw.hardware.fan import Fan
from slafw.hardware.sl1.fan import SL1FanUVLED, SL1FanBlower, SL1FanRear
from slafw.tests.base import SlafwTestCase
from slafw.tests.mocks.motion_controller import MotionControllerMock
from slafw.tests.mocks.temp_sensor import MockTempSensor


class TestFan(Fan):
    AUTO_CONTROL_INTERVAL_S = 0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._target_rpm = 0
        self._running_flag = False

    def save(self, writer: ConfigWriter):
        pass

    @property
    def _running(self):
        return self._running_flag

    @_running.setter
    def _running(self, value: bool):
        self._running_flag = value

    @property
    def rpm(self) -> int:
        return self.target_rpm

    @property
    def error(self) -> bool:
        return False

    @property
    def target_rpm(self) -> int:
        return self._target_rpm

    @target_rpm.setter
    def target_rpm(self, value: int):
        self._target_rpm = value


class OutOfControlExecutor:
    MAX_CONTROL_WAIT_S = 5

    def __init__(self, fan: Fan):
        self._control_running = Lock()
        self._control_performed = Event()

        # Wrap RPM control method to track its execution
        # pylint: disable = protected-access
        orig_rpm_control = fan._fan_rpm_control

        @wraps(fan._fan_rpm_control)
        async def wrapped_rpm_control():
            with self._control_running:
                await orig_rpm_control()
                self._control_performed.set()

        fan._fan_rpm_control = wrapped_rpm_control

    def __enter__(self):
        self._control_running.acquire()
        self._control_performed.clear()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._control_running.release()
        self._control_performed.wait(self.MAX_CONTROL_WAIT_S)


class TestBaseFanFail(SlafwTestCase):
    def test_auto_control_fail_init(self):
        with self.assertRaises(ValueError):
            TestFan("Test", 1000, 2000, 1500, True, auto_control=True)

    def test_auto_control_fail_set(self):
        fan = TestFan("Test", 1000, 2000, 1500, True)
        self.assertFalse(fan.has_auto_control)
        with self.assertRaises(ValueError):
            fan.auto_control = True


class TestBaseFan(SlafwTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_value = Mock(return_value=12)
        self.temp = MockTempSensor("Fake temp", 10, 20, mock_value=self.temp_value)
        self.fan = TestFan("Test", 1000, 2000, 1500, True, reference=self.temp, auto_control=True)
        self.env_setter = OutOfControlExecutor(self.fan)

        self._thread = Thread(target=self._run_components)
        self._task: Optional[asyncio.Task] = None
        self._thread.start()

    def tearDown(self) -> None:
        self._task.cancel()
        self._thread.join()
        super().tearDown()

    def _run_components(self):
        asyncio.run(self._run_components_async())

    async def _run_components_async(self):
        try:
            self._task = asyncio.create_task(self.fan.run())
            await self._task
        except CancelledError:
            pass  # This is standard end of the test
        except Exception:
            logging.getLogger().exception("Test component runner exception")
            raise

    def test_auto_control(self):
        self.assertTrue(self.fan.has_auto_control)
        self.assertTrue(self.fan.auto_control)
        self.fan.running = True
        with self.env_setter:
            self.fan.target_rpm = self.fan.min_rpm
            self.temp_value.return_value = self.temp.max
        self.assertEqual(self.fan.max_rpm, self.fan.target_rpm)

        with self.env_setter:
            self.temp_value.return_value = self.temp.min
        self.assertEqual(self.fan.min_rpm, self.fan.target_rpm)

        with self.env_setter:
            self.temp_value.return_value = (self.temp.min + self.temp.max) / 2
        self.assertEqual((self.fan.min_rpm + self.fan.max_rpm) / 2, self.fan.target_rpm)

    def test_auto_control_disable(self):
        self.fan.running = True
        with self.env_setter:
            self.fan.auto_control = False
            self.fan.target_rpm = self.fan.min_rpm
        self.temp_value.return_value = self.temp.max
        self.assertFalse(self.fan.auto_control)
        self.assertEqual(self.fan.min_rpm, self.fan.target_rpm)

        with self.env_setter:
            self.fan.auto_control = True
        self.assertTrue(self.fan.auto_control)
        self.assertEqual(self.fan.max_rpm, self.fan.target_rpm)


class DoNotRunTestDirectlyFromBaseClass:
    # pylint: disable = too-few-public-methods
    class BaseSL1FanTest(SlafwTestCase, ABC):
        @cached_property
        @abstractmethod
        def fan(self) -> Fan:
            ...

        @property
        @abstractmethod
        def index(self) -> int:
            ...

        def setUp(self) -> None:
            super().setUp()
            self.config = HwConfig()
            self.mcc = MotionControllerMock.get_6c()
            self.temp = MockTempSensor("Fake temp", 10, 20, mock_value=Mock(return_value=20))

        def test_rpm_set(self):
            self.fan.target_rpm = 1000
            self.mcc.set_fan_rpm.assert_called_with(self.index, 1000)

        def test_running_set(self):
            self.fan.running = False
            self.mcc.set_fan_running.assert_called_with(self.index, False)
            self.fan.running = True
            self.mcc.set_fan_running.assert_called_with(self.index, True)

        def test_rpm_read(self):
            callback = Mock(__name__="callback")
            self.fan.rpm_changed.connect(callback)
            rpms = (1111, 2222, 3333)
            self.mcc.fans_rpm_changed.emit(rpms)
            self.assertEqual(rpms[self.index], self.fan.rpm)
            callback.assert_called_with(rpms[self.index])

        def test_error_read(self):
            callback = Mock(__name__="callback")
            self.fan.error_changed.connect(callback)

            self.mcc.fans_error_changed.emit([i == self.index for i in range(3)])
            self.assertEqual(True, self.fan.error)
            callback.assert_called_with(True)

            self.mcc.fans_error_changed.emit([i != self.index for i in range(3)])
            self.assertEqual(False, self.fan.error)
            callback.assert_called_with(False)


class TestSL1FanUVLEDX(DoNotRunTestDirectlyFromBaseClass.BaseSL1FanTest):
    @cached_property
    def fan(self) -> Fan:
        return SL1FanUVLED(self.mcc, self.config, reference=self.temp)

    @property
    def index(self) -> int:
        return 0


class TestSL1FanBlower(DoNotRunTestDirectlyFromBaseClass.BaseSL1FanTest):
    @cached_property
    def fan(self) -> Fan:
        return SL1FanBlower(self.mcc, self.config)

    @property
    def index(self) -> int:
        return 1


class TestSL1FanRear(DoNotRunTestDirectlyFromBaseClass.BaseSL1FanTest):
    @cached_property
    def fan(self) -> Fan:
        return SL1FanRear(self.mcc, self.config)

    @property
    def index(self) -> int:
        return 2


class TestSave(SlafwTestCase):
    def test_save(self):
        config = HwConfig()
        writer = config.get_writer()
        mcc = MotionControllerMock.get_6c()
        temp = MockTempSensor("Fake temp", 10, 20, mock_value=Mock(return_value=20))

        uvled = SL1FanUVLED(mcc, config, reference=temp)
        uvled.enabled = False
        uvled.default_rpm = 2700
        uvled.auto_control = False
        uvled.save(writer)

        blower = SL1FanBlower(mcc, config)
        blower.enabled = False
        blower.default_rpm = 3300
        blower.save(writer)

        rear = SL1FanRear(mcc, config)
        rear.enabled = False
        rear.default_rpm = 5000
        rear.save(writer)

        self.assertFalse(writer.fan1Enabled)
        self.assertEqual(2700, writer.fan1Rpm)
        self.assertFalse(writer.rpmControlUvEnabled)
        self.assertFalse(writer.fan2Enabled)
        self.assertEqual(3300, writer.fan2Rpm)
        self.assertFalse(writer.fan3Enabled)
        self.assertEqual(5000, writer.fan3Rpm)
