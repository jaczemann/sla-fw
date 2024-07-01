# This file is part of the SLA firmware
# Copyright (C) 2020 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio
import logging
from abc import ABC, abstractmethod
from enum import unique, Enum
from typing import Optional, List, Iterable, Dict, Any

from PySignal import Signal

from slafw.states.wizard import WizardCheckState
from slafw.wizard.actions import UserActionBroker
from slafw.wizard.setup import Resource, Configuration
from slafw.wizard.data_package import WizardDataPackage
from slafw.hardware.power_led_action import WarningAction


@unique
class WizardCheckType(Enum):
    UNKNOWN = 0

    TOWER_RANGE = 1
    TOWER_HOME = 2
    TILT_RANGE = 3
    TILT_HOME = 4
    DISPLAY = 5
    CALIBRATION = 6
    MUSIC = 7
    UV_LEDS = 8
    UV_FANS = 9
    MOVE_TO_FOAM = 10
    MOVE_TO_TANK = 11
    RESIN_SENSOR = 12
    SERIAL_NUMBER = 20
    TEMPERATURE = 21
    TILT_CALIBRATION_START = 22
    TILT_CALIBRATION = 23
    TOWER_CALIBRATION = 24
    TILT_TIMING = 25
    SYS_INFO = 26
    CALIBRATION_INFO = 27
    ERASE_PROJECTS = 28
    RESET_HOSTNAME = 29
    RESET_PRUSA_LINK = 30
    RESET_PRUSA_CONNECT = 31
    RESET_NETWORK = 33
    RESET_TIMEZONE = 34
    RESET_NTP = 35
    RESET_LOCALE = 36
    RESET_UV_CALIBRATION_DATA = 37
    REMOVE_SLICER_PROFILES = 38
    RESET_HW_CONFIG = 39
    ERASE_MC_EEPROM = 40
    RESET_MOVING_PROFILES = 41
    SEND_PRINTER_DATA = 42
    DISABLE_FACTORY = 43
    INITIATE_PACKING_MOVES = 44
    FINISH_PACKING_MOVES = 45
    DISABLE_ACCESS = 46
    UV_METER_PRESENT = 60
    UV_WARMUP = 61
    UV_METER_PLACEMENT = 62
    UV_CALIBRATE_CENTER = 63
    UV_CALIBRATE_EDGE = 64
    UV_CALIBRATION_APPLY_RESULTS = 65
    UV_METER_REMOVED = 66
    TILT_LEVEL = 67
    RESET_TOUCH_UI = 68
    ERASE_UV_PWM = 69
    RESET_SELF_TEST = 70
    RESET_MECHANICAL_CALIBRATION = 71
    MARK_PRINTER_MODEL = 72
    RESET_HW_COUNTERS = 73
    RECORD_EXPO_PANEL_LOG = 74

    TOWER_SAFE_DISTANCE = 76
    TOWER_TOUCHDOWN = 77
    EXPOSING_DEBRIS = 78
    TOWER_GENTLY_UP = 79
    WAITING_FOR_USER = 80
    TOWER_HOME_FINISH = 81
    RESET_UPDATE_CHANNEL = 82


class BaseCheck(ABC):
    # pylint: disable=too-many-instance-attributes
    def __init__(
        self,
        check_type: WizardCheckType,
        configuration: Configuration = Configuration(None, None),
        resources: Iterable[Resource] = (),
    ):
        self._logger = logging.getLogger(__name__)
        self._state = WizardCheckState.WAITING
        self._exception: Optional[Exception] = None
        self._warnings: List[Warning] = []
        self._type = check_type
        self._progress: float = 0
        self._configuration = configuration
        self._resources = sorted(resources)
        self.state_changed = Signal()
        self.data_changed = Signal()
        self.exception_changed = Signal()
        self.warnings_changed = Signal()

    @property
    def type(self) -> WizardCheckType:
        return self._type

    @property
    def configuration(self) -> Configuration:
        return self._configuration

    @property
    def resources(self) -> Iterable[Resource]:
        return self._resources

    @property
    def state(self) -> WizardCheckState:
        return self._state

    @state.setter
    def state(self, value: WizardCheckState):
        if self._state != value:
            self._state = value
            self.state_changed.emit()
            self.data_changed.emit()

    @property
    def progress(self) -> float:
        return self._progress

    @progress.setter
    def progress(self, value: float):
        self._logger.debug("Check %s progress: %s", type(self).__name__, value)
        self._progress = value
        self.data_changed.emit()

    @property
    def exception(self) -> Optional[Exception]:
        return self._exception

    @exception.setter
    def exception(self, value: Exception):
        self._exception = value
        self.exception_changed.emit()
        self.data_changed.emit()

    @property
    def warnings(self) -> Iterable[Warning]:
        return self._warnings

    def add_warning(self, warning: Warning):
        self._warnings.append(warning)
        self.warnings_changed.emit()

    @property
    def data(self) -> Dict[str, Any]:
        data = {
            "state": self.state,
            "progress": self._progress,
        }
        return data

    async def run(self, locks: Dict[Resource, asyncio.Lock], actions: UserActionBroker, sync_executor):
        self._logger.info("Locking resources: %s", type(self).__name__)
        for resource in self.resources:
            await locks[resource].acquire()
        self._logger.info("Locked resources: %s", type(self).__name__)

        with WarningAction(actions.led_warn):
            try:
                await asyncio.sleep(0.1)  # This allows to break asyncio program in case the wizard is canceled
                self._logger.info("Running check: %s", type(self).__name__)
                await self.run_wrapper(actions, sync_executor)
            except asyncio.CancelledError:
                self._logger.warning("Check canceled: %s", type(self).__name__)
                self.state = WizardCheckState.CANCELED
                raise
            except Exception as e:
                self._logger.exception("Exception: %s", type(self).__name__)
                self.exception = e
                self.state = WizardCheckState.FAILURE
                raise
            finally:
                self._logger.info("Freeing resources: %s", type(self).__name__)
                for resource in self.resources:
                    locks[resource].release()
                self._logger.info("Freed resources: %s", type(self).__name__)

        if not self.warnings:
            self.state = WizardCheckState.SUCCESS
        else:
            self.state = WizardCheckState.WARNING

        self._logger.info("Done: %s", type(self).__name__)

    @abstractmethod
    async def run_wrapper(self, actions: UserActionBroker, sync_executor):
        ...

    def get_result_data(self) -> Dict[str, Any]:  # pylint: disable = no-self-use
        return {}

    def cancel(self):
        self.state = WizardCheckState.CANCELED


class Check(BaseCheck):
    async def run_wrapper(self, actions: UserActionBroker, sync_executor):
        self.state = WizardCheckState.RUNNING
        self._logger.info("Running: %s (async)", type(self).__name__)
        self.progress = 0
        await self.async_task_run(actions)
        self.progress = 1
        self._logger.info("Done: %s (async)", type(self).__name__)

    @abstractmethod
    async def async_task_run(self, actions: UserActionBroker):
        ...


class SyncCheck(BaseCheck):
    async def run_wrapper(self, actions: UserActionBroker, sync_executor):
        loop = asyncio.get_running_loop()
        self._logger.debug("With thread pool executor: %s", type(self).__name__)
        await loop.run_in_executor(sync_executor, self.sync_run_wrapper, actions)
        self._logger.debug("Done with thread pool executor: %s", type(self).__name__)

    def sync_run_wrapper(self, actions: UserActionBroker):
        self.state = WizardCheckState.RUNNING
        self._logger.info("Running: %s (sync)", type(self).__name__)
        self.progress = 0
        self.task_run(actions)
        self.progress = 1
        self._logger.info("Done: %s (sync)", type(self).__name__)

    @abstractmethod
    def task_run(self, actions: UserActionBroker):
        ...


class DangerousCheck(Check, ABC):
    """
    Dangerous checks require cover closed during operation
    """

    def __init__(self, package: WizardDataPackage, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._package = package

    async def wait_cover_closed(self):
        await asyncio.sleep(0)
        while not self._package.hw.isCoverVirtuallyClosed():
            await asyncio.sleep(0.5)
