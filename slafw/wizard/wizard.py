# This file is part of the SLA firmware
# Copyright (C) 2020-2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio
import logging
from asyncio import CancelledError
from datetime import datetime
from queue import Queue
from shutil import copyfile
from tempfile import NamedTemporaryFile
from threading import Thread
from typing import Iterable, Optional, Dict, Any
from dataclasses import fields

import json as serializer
from PySignal import Signal

from slafw import defines
from slafw.api.decorators import state_checked
from slafw.errors.errors import WizardNotCancelable, FailedToSerializeWizardData, FailedToSaveWizardData, \
    PrinterException
from slafw.errors.warnings import PrinterWarning
from slafw.functions.system import FactoryMountedRW
from slafw.states.wizard import WizardState, WizardCheckState, WizardId
from slafw.wizard.wizards.generic import ShowResultsGroup
from slafw.wizard.actions import UserActionBroker, PushState
from slafw.wizard.checks.base import Check, WizardCheckType, DangerousCheck
from slafw.wizard.group import CheckGroup, SingleCheckGroup
from slafw.wizard.data_package import WizardDataPackage


class Wizard(Thread, UserActionBroker):
    # pylint: disable=too-many-instance-attributes
    # pylint: disable=too-many-arguments
    # pylint: disable=too-many-public-methods

    def __init__(
        self,
        identifier: WizardId,
        groups: Iterable[CheckGroup],
        package: WizardDataPackage,
        cancelable=True,
    ):
        self._logger = logging.getLogger(__name__)
        Thread.__init__(self)
        UserActionBroker.__init__(self, package.hw)
        self._config_writers = package.config_writers
        self.__state = WizardState.INIT
        self.__cancelable = cancelable
        self.__groups = groups
        self.__identifier = identifier
        self.started_changed = Signal()
        self.state_changed = Signal()
        self.check_states_changed = Signal()
        self.check_data_changed = Signal()
        self.exception_changed = Signal()
        self.warnings_changed = Signal()
        self.__current_group: Optional[CheckGroup] = None
        self.unstop_result: Queue[bool] = Queue()  # pylint: disable=unsubscriptable-object
        self._runtime_config = package.runtime_config
        self.started = datetime.now()
        self._dangerous_running = False
        self._close_cover_state: Optional[PushState] = None
        self._data: Dict[str, Any] = {}
        self.data_changed = Signal()
        self._exception: Optional[Exception] = None

        for check in self.checks:
            check.state_changed.connect(self.check_states_changed.emit)
            check.state_changed.connect(self._update_state)
            check.state_changed.connect(self._update_data)
            check.exception_changed.connect(self.exception_changed.emit)
            check.warnings_changed.connect(self.warnings_changed.emit)
            check.data_changed.connect(self.check_data_changed.emit)

        self.states_changed.connect(self._update_state)
        self.check_states_changed.connect(self._update_dangerous_check_running)
        self._hw.cover_state_changed.connect(self._check_cover_closed)

    @property
    def identifier(self) -> WizardId:
        return self.__identifier

    def _update_state(self):
        # TODO: This is not nice, maybe we would like to compute wizard state just using the inner check states.
        # TODO: Feel free to refactor this if the current structure is not fit for new features.
        if self.state in [WizardState.FAILED, WizardState.CANCELED, WizardState.STOPPED, WizardState.DONE]:
            return

        if self._states:
            self.state = self._states[0].state
            return

        if any([check.state == WizardCheckState.RUNNING for check in self.checks]):
            self.state = WizardState.RUNNING

    @property
    def state(self) -> WizardState:
        return self.__state

    @state.setter
    def state(self, value: WizardState):
        if value != self.__state:
            self.__state = value
            self.state_changed.emit(value)

    @property
    def cancelable(self):
        return self.__cancelable

    @property
    def checks(self) -> Iterable[Check]:
        for group in self.__groups:
            for check in group.checks:
                yield check

    @property
    def exception(self) -> Optional[Exception]:
        if self._exception:
            return self._exception

        for check in self.checks:
            if check.exception:
                return check.exception

        return None

    @property
    def warnings(self) -> Iterable[PrinterWarning]:
        for check in self.checks:
            for warning in check.warnings:
                yield warning

    @property
    def dangerous_check_running(self) -> bool:
        return self._dangerous_running

    @property
    def check_state(self) -> Dict[WizardCheckType, WizardCheckState]:
        return {check.type: check.state for check in self.checks}

    @property
    def check_data(self) -> Dict[WizardCheckType, Dict[str, Any]]:
        return {check.type: check.data for check in self.checks}

    @property
    def data(self) -> Dict[str, Any]:
        return self._data

    def run(self):
        self._logger.info("Wizard %s running", type(self).__name__)
        self.started_changed.emit()
        self.check_states_changed.emit()

        try:
            for group in self.__groups:
                self.__current_group = group
                self.__run_group(group)
                self.__current_group = None
            for group in self.__groups:
                for check in group.checks:
                    self._logger.debug("Running wizard finished for %s", type(check).__name__)
            self.wizard_finished()
            for field in fields(self._config_writers):
                getattr(self._config_writers, field.name).commit()
            self._store_data()
        except CancelledError:
            self._logger.debug("Wizard group canceled successfully")
            self.state = WizardState.CANCELED
        except Exception as exception:
            self._exception = exception
            self.exception_changed.emit()
            self.state = WizardState.FAILED
            self.wizard_failed()
            self._store_data()
            raise
        finally:
            self._hw.motors_release()
            if self.state not in [WizardState.CANCELED, WizardState.FAILED]:
                self.state = WizardState.DONE
            self._logger.info("Wizard %s finished with state %s", type(self).__name__, self.state)

    def cancel(self):
        if not self.cancelable:
            raise WizardNotCancelable()
        self.force_cancel()

    def force_cancel(self):
        self._logger.info("Canceling wizard")

        if self.__current_group:
            self._logger.debug("Canceling running wizard group")
            self.__current_group.cancel()

    def wizard_finished(self):
        """custom wizard action which is called on wizard success"""

    def wizard_failed(self):
        """custom wizard action which is called on wizard failure"""

    def __run_group(self, group: CheckGroup):
        self._logger.debug("Running check group %s", type(group).__name__)
        asyncio.run(group.run(self))

# retry implementation
#        while True:
#            try:
#                asyncio.run(group.run(self))
#                break
#            except (CancelledError, PrinterException):
#                self.state = WizardState.STOPPED
#                self._hw.motors_release()
#                self._logger.exception("Wizard group stopped by exception")
#                if not self.unstop_result.get():
#                    raise
#                self.state = WizardState.RUNNING

    @state_checked(WizardState.STOPPED)
    def abort(self):
        self._logger.info("Aborting wizard")
        self.unstop_result.put(False)

    @state_checked(WizardState.STOPPED)
    def retry(self):
        self._logger.info("Retrying wizard")
        self.unstop_result.put(True)

    def _update_data(self):
        self._data = self._get_data()
        self.data_changed.emit()

    def _get_data(self) -> Dict[str, Any]:
        data = {}
        for group in self.__groups:
            for check in group.checks:
                if check.state == WizardCheckState.SUCCESS:
                    data.update(check.get_result_data())
                elif check.state == WizardCheckState.FAILURE:
                    data[f"{type(check).__name__.lower()}_exception"] = PrinterException.as_dict(check.exception)
        return data

    @classmethod
    def get_name(cls) -> str:
        return cls.__name__.lower()

    @classmethod
    def get_data_filename(cls) -> str:
        return f"{cls.get_name()}_data.{serializer.__name__}"

    @classmethod
    def get_alt_names(cls) -> Iterable[str]:
        return (cls.get_data_filename(),)

    @property
    def history_data_filename(self) -> str:
        return f"{self.get_name()}_data.{self.started.strftime('%Y-%m-%d_%H-%M-%S')}.{serializer.__name__}"

    def _data_present_in_factory(self) -> bool:
        return any([list(defines.factoryMountPoint.glob(name + "*")) for name in self.get_alt_names()])

    def _store_data(self):
        with NamedTemporaryFile(mode="wt", encoding="utf-8") as temp:
            try:
                self._logger.debug("Wizard data to store: %s", self.data)
                if not self.data:
                    self._logger.info("Not saving empty wizard data")
                    return
                # TODO variable options for serializer different from json
                serializer.dump(self.data, temp, indent=2, sort_keys=True)
                temp.flush()
            except Exception as exception:
                raise FailedToSerializeWizardData() from exception

            try:
                # Store as current wizard result in factory (in case it is already not present i.e. from factory setup)
                # Also store result in factory in case of active factory mode
                if not self._data_present_in_factory() or self._runtime_config.factory_mode:
                    with FactoryMountedRW():
                        copyfile(temp.name, defines.factoryMountPoint / self.get_data_filename())
                        defines.wizardHistoryPathFactory.mkdir(parents=True, exist_ok=True)
                        copyfile(temp.name, defines.wizardHistoryPathFactory / self.history_data_filename)
                else:
                    # Store as current wizard result in etc
                    copyfile(temp.name, defines.configDir / self.get_data_filename())
                    defines.wizardHistoryPath.mkdir(parents=True, exist_ok=True)
                    copyfile(temp.name, defines.wizardHistoryPath / self.history_data_filename)

            except Exception as exception:
                raise FailedToSaveWizardData() from exception
        self._logger.info("Wizard %s data stored", type(self).__name__)

    def _update_dangerous_check_running(self):
        self._dangerous_running = self.__current_group and any(
            [
                isinstance(check, DangerousCheck) and check.state == WizardCheckState.RUNNING
                for check in self.__current_group.checks
            ]
        )
        self._check_cover_closed(self._hw.isCoverClosed())

    def _check_cover_closed(self, closed: bool):
        self._logger.debug("Checking cover closed: %s", closed)
        if self.dangerous_check_running and self._hw.config.coverCheck and not closed and not self._close_cover_state:
            self._logger.warning("Cover open and dangerous check running, pushing close cover state")
            self._close_cover_state = PushState(WizardState.CLOSE_COVER)
            self.push_state(self._close_cover_state, priority=True)
            return

        if self._close_cover_state:
            self._logger.debug("Danger from closed cover neutralized, dropping close cover state")
            self.drop_state(self._close_cover_state)
            self._close_cover_state = None


class SingleCheckWizard(Wizard):
    # pylint: disable=too-many-arguments
    def __init__(
        self,
        identifier: WizardId,
        check: Check,
        package: WizardDataPackage,
        cancelable=True,
        show_results=True,
    ):
        groups = [SingleCheckGroup(check)]
        if show_results:
            groups.append(ShowResultsGroup())
        super().__init__(identifier, groups, package, cancelable)
