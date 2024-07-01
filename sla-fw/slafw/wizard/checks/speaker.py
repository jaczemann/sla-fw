# This file is part of the SLA firmware
# Copyright (C) 2020 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from asyncio import Event, AbstractEventLoop, get_running_loop
from functools import partial
from typing import Optional

from slafw.errors.errors import SoundTestFailed
from slafw.states.wizard import WizardState
from slafw.wizard.actions import UserActionBroker, PushState
from slafw.wizard.checks.base import Check, WizardCheckType
from slafw.wizard.setup import Configuration


class SpeakerTest(Check):
    def __init__(self):
        super().__init__(WizardCheckType.MUSIC, Configuration(None, None), [])
        self.result: Optional[bool] = None
        self._user_event: Optional[Event] = None

    async def async_task_run(self, actions: UserActionBroker):
        self._user_event = Event()
        self.result = None
        self._user_event.clear()

        actions.report_audio.register_callback(partial(self.user_callback, get_running_loop()))
        push_state = PushState(WizardState.TEST_AUDIO)
        actions.push_state(push_state)

        await self._user_event.wait()

        actions.drop_state(push_state)
        actions.report_audio.unregister_callback()
        if not self.result:
            self._logger.error("Sound test failed")
            raise SoundTestFailed()

    def user_callback(self, loop: AbstractEventLoop, result: bool):
        self.result = result
        loop.call_soon_threadsafe(self._user_event.set)
