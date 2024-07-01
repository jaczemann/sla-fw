# This file is part of the SLA firmware
# Copyright (C) 2020 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from slafw.states.wizard import WizardId
from slafw.states.wizard import WizardState
from slafw.wizard.actions import UserActionBroker
from slafw.wizard.checks.display import DisplayTest
from slafw.wizard.checks.uvleds import UVLEDsTest
from slafw.wizard.group import CheckGroup
from slafw.wizard.setup import Configuration, TankSetup
from slafw.wizard.wizard import Wizard
from slafw.wizard.data_package import WizardDataPackage
from slafw.wizard.wizards.generic import ShowResultsGroup


class DisplayTestCheckGroup(CheckGroup):
    def __init__(self, package: WizardDataPackage):
        super().__init__(
            Configuration(TankSetup.REMOVED, None),
            [
                UVLEDsTest(package),
                DisplayTest(package),
            ],
        )

    async def setup(self, actions: UserActionBroker):
        await self.wait_for_user(actions, actions.prepare_displaytest_done,
                                 WizardState.PREPARE_DISPLAY_TEST)


class DisplayTestWizard(Wizard):
    def __init__(self, package: WizardDataPackage):
        super().__init__(
            WizardId.DISPLAY,
            [
                DisplayTestCheckGroup(package),
                ShowResultsGroup(),
            ],
            package,
        )

    @classmethod
    def get_name(cls) -> str:
        return "display_test"
