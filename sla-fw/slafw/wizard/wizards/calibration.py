# This file is part of the SLA firmware
# Copyright (C) 2020-2024 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from slafw.states.wizard import WizardId
from slafw.states.wizard import WizardState
from slafw.wizard.actions import UserActionBroker
from slafw.wizard.checks.tank_surface_cleaner import HomeTowerFinish
from slafw.wizard.checks.tilt import (
    TiltHomeTest,
    TiltCalibrationStartTest,
    TiltAlignTest
)
from slafw.wizard.checks.sysinfo import SystemInfoTest
from slafw.wizard.checks.tower import TowerAlignTest, TowerHomeTest
from slafw.wizard.group import CheckGroup
from slafw.wizard.setup import Configuration, TankSetup, PlatformSetup
from slafw.wizard.wizard import Wizard
from slafw.wizard.data_package import WizardDataPackage
from slafw.wizard.wizards.generic import ShowResultsGroup


class PlatformTankInsertCheckGroup(CheckGroup):
    def __init__(self, package: WizardDataPackage):
        super().__init__(
            Configuration(None, None),
            [
                TiltHomeTest(package),
                TowerHomeTest(package),
                TiltCalibrationStartTest(package),
                SystemInfoTest(package),
            ],
        )

    async def setup(self, actions: UserActionBroker):
        await self.wait_for_user(
            actions,
            actions.prepare_calibration_platform_tank_done,
            WizardState.PREPARE_CALIBRATION_INSERT_PLATFORM_TANK,
        )


class TiltAlignCheckGroup(CheckGroup):
    def __init__(self, package: WizardDataPackage):
        super().__init__(
            Configuration(TankSetup.REMOVED, None),
            [TiltAlignTest(package)],
        )

    async def setup(self, actions: UserActionBroker):
        await self.wait_for_user(
            actions,
            actions.prepare_calibration_tilt_align_done,
            WizardState.PREPARE_CALIBRATION_TILT_ALIGN,
        )


class PlatformAlignCheckGroup(CheckGroup):
    def __init__(self, package: WizardDataPackage):
        super().__init__(
            Configuration(TankSetup.PRINT, PlatformSetup.PRINT),
            [TowerAlignTest(package)],
        )

    async def setup(self, actions: UserActionBroker):
        await self.wait_for_user(
            actions,
            actions.prepare_calibration_platform_align_done,
            WizardState.PREPARE_CALIBRATION_PLATFORM_ALIGN,
        )


class CalibrationFinishCheckGroup(CheckGroup):
    def __init__(self, package: WizardDataPackage):
        super().__init__(
            Configuration(TankSetup.PRINT, PlatformSetup.PRINT),
            [HomeTowerFinish(package)],
        )

    async def setup(self, actions: UserActionBroker):
        await self.wait_for_user(
            actions,
            actions.prepare_calibration_finish_done,
            WizardState.PREPARE_CALIBRATION_FINISH,
        )


class CalibrationWizard(Wizard):
    def __init__(self, package: WizardDataPackage):
        super().__init__(
            WizardId.CALIBRATION,
            [
                PlatformTankInsertCheckGroup(package),
                TiltAlignCheckGroup(package),
                PlatformAlignCheckGroup(package),
                CalibrationFinishCheckGroup(package),
                ShowResultsGroup(),
            ],
            package,
        )
        self._package = package

    @classmethod
    def get_name(cls) -> str:
        return "calibration"

    def wizard_finished(self):
        self._config_writers.hw_config.calibrated = True

    def wizard_failed(self):
        writer = self._package.hw.config.get_writer()
        writer.calibrated = False
        writer.commit()
