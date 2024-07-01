# This file is part of the SLA firmware
# Copyright (C) 2020 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Iterable

from slafw.states.wizard import WizardId
from slafw.states.wizard import WizardState
from slafw.wizard.actions import UserActionBroker
from slafw.wizard.checks.unboxing import MoveToTank, MoveToFoam
from slafw.wizard.group import CheckGroup
from slafw.wizard.setup import Configuration
from slafw.wizard.wizard import Wizard
from slafw.wizard.data_package import WizardDataPackage
from slafw.wizard.wizards.generic import ShowResultsGroup


class RemoveSafetyStickerCheckGroup(CheckGroup):
    def __init__(self, package: WizardDataPackage):
        super().__init__(Configuration(None, None), [MoveToFoam(package)])

    async def setup(self, actions: UserActionBroker):
        await self.wait_for_user(actions, actions.safety_sticker_removed, WizardState.REMOVE_SAFETY_STICKER)


class RemoveSideFoamCheckGroup(CheckGroup):
    def __init__(self, package: WizardDataPackage):
        super().__init__(Configuration(None, None), [MoveToTank(package)])

    async def setup(self, actions: UserActionBroker):
        await self.wait_for_user(actions, actions.side_foam_removed, WizardState.REMOVE_SIDE_FOAM)


class RemoveTankFoamCheckGroup(CheckGroup):
    def __init__(self):
        super().__init__(Configuration(None, None), [])

    async def setup(self, actions: UserActionBroker):
        await self.wait_for_user(actions, actions.tank_foam_removed, WizardState.REMOVE_TANK_FOAM)


class RemoveDisplayFoilCheckGroup(CheckGroup):
    def __init__(self):
        super().__init__(Configuration(None, None), [])

    async def setup(self, actions: UserActionBroker):
        await self.wait_for_user(actions, actions.display_foil_removed, WizardState.REMOVE_DISPLAY_FOIL)


class UnboxingWizard(Wizard):
    # pylint: disable = too-many-arguments
    def __init__(self, identifier, groups: Iterable[CheckGroup], package: WizardDataPackage):
        super().__init__(identifier, groups, package, cancelable=False)

    def wizard_finished(self):
        self._config_writers.hw_config.showUnboxing = False


class CompleteUnboxingWizard(UnboxingWizard):
    def __init__(self, package: WizardDataPackage):
        super().__init__(
            WizardId.COMPLETE_UNBOXING,
            [
                RemoveSafetyStickerCheckGroup(package),
                RemoveSideFoamCheckGroup(package),
                RemoveTankFoamCheckGroup(),
                RemoveDisplayFoilCheckGroup(),
                ShowResultsGroup(),
            ],
            package,
        )

    @classmethod
    def get_name(cls) -> str:
        return "complete_unboxing"


class KitUnboxingWizard(UnboxingWizard):
    def __init__(self, package: WizardDataPackage):
        super().__init__(WizardId.KIT_UNBOXING, [RemoveDisplayFoilCheckGroup(), ShowResultsGroup()], package)

    @classmethod
    def get_name(cls) -> str:
        return "kit_unboxing"
