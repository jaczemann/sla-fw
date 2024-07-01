# This file is part of the SLA firmware
# Copyright (C) 2020 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio
import functools
import logging
from abc import ABC, abstractmethod
from asyncio import Future, AbstractEventLoop
from concurrent.futures.thread import ThreadPoolExecutor
from typing import Iterable, Optional, Dict

from slafw.states.wizard import WizardState, WizardCheckState
from slafw.wizard.actions import UserActionBroker, UserAction, PushState
from slafw.wizard.checks.base import BaseCheck
from slafw.wizard.setup import Resource, Configuration


class CheckGroup(ABC):
    MAX_PARALLEL_SYNC_TASKS = 3

    def __init__(self, configuration: Configuration = Configuration(None, None), checks: Iterable[BaseCheck] = ()):
        self._logger = logging.getLogger(__name__)
        if not all([configuration.is_compatible(check.configuration) for check in checks]):
            raise ValueError("Check does not match group configuration")
        self._configuration = configuration
        self._checks = checks
        self._locks: Optional[Dict[Resource, asyncio.Lock]] = None
        self._future: Optional[Future] = None
        self._loop: Optional[AbstractEventLoop] = None

    @abstractmethod
    async def setup(self, actions: UserActionBroker):
        ...

    @property
    def checks(self) -> Iterable[BaseCheck]:
        return self._checks

    async def wait_for_user(self, actions: UserActionBroker, action: UserAction, state: WizardState):
        done = asyncio.Event()
        wait_state = PushState(state)

        def callback(loop: AbstractEventLoop):
            loop.call_soon_threadsafe(done.set)

        try:
            action.register_callback(functools.partial(callback, asyncio.get_running_loop()))
            actions.push_state(wait_state)
            self._logger.debug("Waiting for user action: %s", state)
            await done.wait()
        finally:
            action.unregister_callback()
            actions.drop_state(wait_state)

    async def run(self, actions: UserActionBroker):
        self._loop = asyncio.get_running_loop()
        with ThreadPoolExecutor(max_workers=self.MAX_PARALLEL_SYNC_TASKS) as sync_executor:
            self._future = asyncio.create_task(self.run_tasks(actions, sync_executor))
            await self._future

    async def run_tasks(self, actions: UserActionBroker, sync_executor):
        self._init_locks()  # Locks has to be initialized from a running event loop
        self._logger.info("Running group setup")
        await self.setup(actions)
        self._logger.info("Running non-finished group tasks")
        tasks = [check.run(self._locks, actions, sync_executor) for check in self._checks if check.state != WizardCheckState.SUCCESS]
        await asyncio.gather(*tasks)
        self._logger.info("Group tasks done")

    def cancel(self):
        self._logger.debug("Check group cancel")
        if self._future and self._loop:
            self._logger.debug("Canceling check group future")
            self._loop.call_soon_threadsafe(self._future.cancel)
            for check in self.checks:
                check.cancel()

    def _init_locks(self):
        # pylint: disable = no-member
        self._locks = {resource: asyncio.Lock() for resource in Resource.__members__.values()}


class SingleCheckGroup(CheckGroup):

    def __init__(self, check: BaseCheck):
        super().__init__(checks=(check,))

    async def setup(self, actions: UserActionBroker):
        pass
