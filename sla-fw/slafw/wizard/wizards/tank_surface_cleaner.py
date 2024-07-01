# This file is part of the SLA firmware
# Copyright (C) 2020 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from slafw.wizard.checks.tank_surface_cleaner import HomeTower, TiltHome, TiltUp, TowerSafeDistance, TouchDown, \
    GentlyUp, ExposeDebris, HomeTowerFinish, Check, Calibrated
from slafw.wizard.group import SingleCheckGroup, CheckGroup
from slafw.wizard.wizard import WizardId, Wizard, WizardState
from slafw.wizard.data_package import WizardDataPackage
from slafw.wizard.actions import UserActionBroker


class InitGroup(SingleCheckGroup):
    """ Dummy group to pause execution on init """
    def __init__(self, check: Check):
        super().__init__(check)

    async def setup(self, actions: UserActionBroker):
        await self.wait_for_user(actions, actions.tank_surface_cleaner_init_done, WizardState.TANK_SURFACE_CLEANER_INIT)


class InsertCleaningAdaptorGroup(SingleCheckGroup):
    """ Group to pause execution on for cleaning adaptor insertion """
    def __init__(self, check: Check):
        super().__init__(check)

    async def setup(self, actions: UserActionBroker):
        await self.wait_for_user(actions, actions.insert_cleaning_adaptor_done, WizardState.TANK_SURFACE_CLEANER_INSERT_CLEANING_ADAPTOR)


class RemoveCleaningAdaptorGroup(CheckGroup):
    """ Group to pause execution on for cleaning adaptor removal """
    def __init__(self):
        super().__init__()

    async def setup(self, actions: UserActionBroker):
        await self.wait_for_user(actions, actions.remove_cleaning_adaptor_done, WizardState.TANK_SURFACE_CLEANER_REMOVE_CLEANING_ADAPTOR)


class TankSurfaceCleaner(Wizard):
    """
    - init
    - home platform
    - home tank (down)
    - level tank
    - platform down to the safe distance
    - platform down until it touches the cleaning adaptor against the bottom of the tank(raise exception
      if cleaning adaptor is missing)
    - gently move the platform up to the safe distance so as to not tear the exposed film of resin
    - move the platform up so that the user can remove the garbage
    """

    def __init__(self, package: WizardDataPackage):
        super().__init__(
            WizardId.TANK_SURFACE_CLEANER,
            [
                SingleCheckGroup(Calibrated(package)),
                InitGroup(HomeTower(package)),
                SingleCheckGroup(TiltHome(package)),
                SingleCheckGroup(TiltUp(package)),
                InsertCleaningAdaptorGroup(TowerSafeDistance(package)),
                SingleCheckGroup(TouchDown(package)),
                SingleCheckGroup(ExposeDebris(package)),
                SingleCheckGroup(GentlyUp(package)),
                SingleCheckGroup(HomeTowerFinish(package)),
                RemoveCleaningAdaptorGroup(),
            ],
            package,
        )

    @classmethod
    def get_name(cls) -> str:
        return "tank_surface_cleaner"
