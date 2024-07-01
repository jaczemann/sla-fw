# This file is part of the SLA firmware
# Copyright (C) 2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from slafw.functions.system import shut_down
from slafw.states.wizard import WizardId, WizardState
from slafw.wizard.actions import UserActionBroker
from slafw.wizard.checks.factory_reset import (
    DisableFactory,
    ResetHostname,
    ResetPrusaLink,
    ResetPrusaConnect,
    ResetNetwork,
    ResetTimezone,
    ResetNTP,
    ResetLocale,
    ResetUVCalibrationData,
    RemoveSlicerProfiles,
    ResetHWConfig,
    EraseMCEeprom,
    ResetMovingProfiles,
    EraseProjects,
    SendPrinterData,
    InitiatePackingMoves,
    FinishPackingMoves,
    DisableAccess,
    ResetTouchUI,
    ResetUpdateChannel,
)
from slafw.wizard.group import CheckGroup
from slafw.wizard.setup import Configuration
from slafw.wizard.wizard import Wizard
from slafw.wizard.data_package import WizardDataPackage


class ResetSettingsGroup(CheckGroup):
    def __init__(
        self,
        package: WizardDataPackage,
        disable_unboxing: bool,
        erase_projects: bool = False,
        hard_errors: bool = False,
    ):
        checks = [
            ResetHostname(hard_errors=hard_errors),
            ResetPrusaLink(hard_errors=hard_errors),
            ResetPrusaConnect(hard_errors=hard_errors),
            ResetNetwork(hard_errors=hard_errors),
            ResetTimezone(hard_errors=hard_errors),
            ResetNTP(hard_errors=hard_errors),
            ResetLocale(hard_errors=hard_errors),
            ResetUVCalibrationData(hard_errors=hard_errors),
            RemoveSlicerProfiles(hard_errors=hard_errors),
            ResetHWConfig(package, disable_unboxing=disable_unboxing, hard_errors=hard_errors),
            DisableAccess(),
            ResetTouchUI(),
            ResetUpdateChannel(hard_errors=hard_errors),
        ]
        if erase_projects:
            checks.append(EraseProjects(hard_errors=hard_errors))
        super().__init__(Configuration(None, None), checks)

    async def setup(self, actions: UserActionBroker):
        pass


class SendPrinterDataGroup(CheckGroup):
    def __init__(self, package: WizardDataPackage):
        super().__init__(Configuration(None, None), [SendPrinterData(package)])

    async def setup(self, actions: UserActionBroker):
        pass


class PackStage1(CheckGroup):
    def __init__(
        self, package: WizardDataPackage, packs_moves: bool = True,
    ):
        checks = [DisableFactory()]
        if packs_moves:
            checks.append(InitiatePackingMoves(package))
        super().__init__(Configuration(None, None), checks)

    async def setup(self, actions: UserActionBroker):
        pass


class FinishResetSettingsGroup(CheckGroup):
    """
    Finish resetting the printer settings. After running this group,
    the printer should avoid homing and preferably even moving at all,
    because the needed profiles have been reset.
    """
    def __init__(self, package: WizardDataPackage, hard_errors: bool = False):
        super().__init__(Configuration(None, None), [
            ResetMovingProfiles(package, hard_errors=hard_errors),
            EraseMCEeprom(package, hard_errors=hard_errors),
        ])

    async def setup(self, actions: UserActionBroker):
        pass


class PackStage2(CheckGroup):
    def __init__(self, package: WizardDataPackage):
        super().__init__(Configuration(None, None), [FinishPackingMoves(package)])

    async def setup(self, actions: UserActionBroker):
        await self.wait_for_user(actions, actions.foam_inserted, WizardState.INSERT_FOAM)


class FactoryResetWizard(Wizard):
    # pylint: disable=too-many-arguments
    def __init__(self, package: WizardDataPackage, erase_projects: bool = False):
        super().__init__(
            WizardId.FACTORY_RESET,
            [
                ResetSettingsGroup(package, True, erase_projects),
                FinishResetSettingsGroup(package),
            ],
            package,
        )

    def run(self):
        super().run()
        shut_down(self._hw, reboot=True)


class PackingWizard(Wizard):
    def __init__(self, package: WizardDataPackage):
        groups = [
            SendPrinterDataGroup(package),
            ResetSettingsGroup(package, disable_unboxing=False, erase_projects=False, hard_errors=True),
        ]
        if package.hw.isKit:
            groups.append(PackStage1(package, False))
        else:
            groups.append(PackStage1(package, True))
            groups.append(PackStage2(package))

        groups.append(FinishResetSettingsGroup(package, hard_errors=True))

        super().__init__(WizardId.PACKING, groups, package)

    def run(self):
        super().run()
        if self.state == WizardState.DONE:
            shut_down(self._hw)
