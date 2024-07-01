# This file is part of the SLA firmware
# Copyright (C) 2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from slafw.wizard.group import CheckGroup
from slafw.wizard.actions import UserActionBroker
from slafw.states.wizard import WizardState


class ShowResultsGroup(CheckGroup):
    def __init__(self):
        super().__init__()

    async def setup(self, actions: UserActionBroker):
        await self.wait_for_user(actions, actions.show_results_done, WizardState.SHOW_RESULTS)
