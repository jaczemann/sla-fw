# This file is part of the SLA firmware
# Copyright (C) 2020 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from asyncio import sleep
from typing import Optional

from slafw.configs.unit import Nm
from slafw.wizard.data_package import WizardDataPackage
from slafw.wizard.actions import UserActionBroker
from slafw.wizard.checks.base import WizardCheckType, Check
from slafw.wizard.setup import Configuration, Resource


class MoveToFoam(Check):
    FOAM_TARGET_POSITION_NM = Nm(30_000_000)

    def __init__(self, package: WizardDataPackage):
        super().__init__(
            WizardCheckType.MOVE_TO_FOAM, Configuration(None, None), [Resource.TOWER_DOWN, Resource.TOWER],
        )
        self._result: Optional[bool] = None
        self._hw = package.hw

    async def async_task_run(self, actions: UserActionBroker):
        self._hw.tower.position = Nm(0)
        self._hw.tower.actual_profile = self._hw.tower.profiles.homingFast
        initial_pos_nm = self._hw.tower.position
        self._hw.tower.move(self.FOAM_TARGET_POSITION_NM)
        while self._hw.tower.moving:
            if self.FOAM_TARGET_POSITION_NM != initial_pos_nm:
                self.progress = (self._hw.tower.position - initial_pos_nm) / (
                    self.FOAM_TARGET_POSITION_NM - initial_pos_nm
                )
            else:
                self.progress = 1
            await sleep(0.5)
        self._hw.tower.release()


class MoveToTank(Check):
    def __init__(self, package: WizardDataPackage):
        super().__init__(
            WizardCheckType.MOVE_TO_TANK, Configuration(None, None), [Resource.TOWER_DOWN, Resource.TOWER],
        )
        self._result: Optional[bool] = None
        self._hw = package.hw

    async def async_task_run(self, actions: UserActionBroker):
        await self._hw.tower.sync_ensure_async(retries=3)  # Let this fail fast, allow for proper tower synced check
        self._hw.tower.release()
