# This file is part of the SLA firmware
# Copyright (C) 2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Iterable

from slafw.errors.errors import PrinterError
from slafw.libUvLedMeterMulti import UvLedMeterMulti, UVCalibrationResult
from slafw.states.wizard import WizardId
from slafw.states.wizard import WizardState
from slafw.wizard.actions import UserActionBroker
from slafw.wizard.checks.display import DisplayTest
from slafw.wizard.checks.sysinfo import SystemInfoTest
from slafw.wizard.checks.uv_calibration import (
    CheckUVMeter,
    UVWarmupCheck,
    CheckUVMeterPlacement,
    UVCalibrateCenter,
    UVCalibrateEdge,
    UVCalibrateApply,
    UVRemoveCalibrator,
)
from slafw.wizard.checks.uvleds import UVLEDsTest
from slafw.wizard.group import CheckGroup
from slafw.wizard.setup import Configuration, TankSetup, PlatformSetup
from slafw.wizard.wizard import Wizard
from slafw.wizard.data_package import WizardDataPackage


# pylint: disable = too-many-arguments


class UVCalibrationPrepare(CheckGroup):
    def __init__(self, package: WizardDataPackage):
        super().__init__(
            Configuration(TankSetup.REMOVED, PlatformSetup.PRINT),
            [
                UVLEDsTest(package),
                DisplayTest(package),
                SystemInfoTest(package),
            ],
        )
        self._package = package

    async def setup(self, actions: UserActionBroker):
        if not self._package.hw.printer_model.options.has_UV_calibration:  # type: ignore[attr-defined]
            raise PrinterError("UV calibration does not work on this printer model")
        await self.wait_for_user(actions, actions.uv_calibration_prepared, WizardState.UV_CALIBRATION_PREPARE)


class UVCalibrationPlaceUVMeter(CheckGroup):
    # TODO: Checks are run in parallel within the group. This group would make a use of strict serial execution.
    # TODO: Currently this is achieved as a side effect of locking the resources. Explicit serial execution is
    # TODO: appreciated.
    def __init__(self, package: WizardDataPackage, uv_meter: UvLedMeterMulti):
        super().__init__(
            Configuration(TankSetup.PRINT, PlatformSetup.PRINT),
            [
                CheckUVMeter(package, uv_meter),
                UVWarmupCheck(package),
                CheckUVMeterPlacement(package, uv_meter),
            ],
        )

    async def setup(self, actions: UserActionBroker):
        await self.wait_for_user(actions, actions.uv_meter_placed, WizardState.UV_CALIBRATION_PLACE_UV_METER)


class UVCalibrationCalibrate(CheckGroup):
    # TODO: Checks are run in parallel within the group. This group would make a use of strict serial execution.
    # TODO: Currently this is achieved as a side effect of locking the resources. Explicit serial execution is
    # TODO: appreciated.
    def __init__(self,
            package: WizardDataPackage,
            uv_meter: UvLedMeterMulti,
            uv_result: UVCalibrationResult,
            replacement: bool,
    ):
        super().__init__(
            Configuration(TankSetup.PRINT, PlatformSetup.PRINT),
            [
                UVCalibrateCenter(package, uv_meter, uv_result, replacement),
                UVCalibrateEdge(package, uv_meter, uv_result, replacement),
            ],
        )

    async def setup(self, actions: UserActionBroker):
        # No initial actions, connect to previous group?
        pass


class UVCalibrationFinish(CheckGroup):
    def __init__(self,
            package: WizardDataPackage,
            uv_meter: UvLedMeterMulti,
            uv_result: UVCalibrationResult,
            display_replaced: bool,
            led_module_replaced: bool,
    ):
        super().__init__(
            Configuration(TankSetup.PRINT, PlatformSetup.PRINT),
            [
                UVRemoveCalibrator(uv_meter),
                UVCalibrateApply(package, uv_result, display_replaced, led_module_replaced
                ),
            ],
        )

    async def setup(self, actions: UserActionBroker):
        # No initial actions, connect to previous group?
        pass


class UVCalibrationWizard(Wizard):
    def __init__(self, package: WizardDataPackage, display_replaced: bool, led_module_replaced: bool):
        self._package = package
        self._uv_meter = UvLedMeterMulti()
        uv_result = UVCalibrationResult()
        super().__init__(
            WizardId.UV_CALIBRATION,
            [
                UVCalibrationPrepare(package),
                UVCalibrationPlaceUVMeter(package, self._uv_meter),
                UVCalibrationCalibrate(package, self._uv_meter, uv_result, display_replaced or led_module_replaced),
                UVCalibrationFinish(package, self._uv_meter, uv_result, display_replaced, led_module_replaced),
            ],
            package,
        )

    @classmethod
    def get_alt_names(cls) -> Iterable[str]:
        names = ["uvcalib_data.toml"]
        names.extend(super().get_alt_names())
        return names

    @classmethod
    def get_name(cls) -> str:
        return "uv_calibration"

    def run(self):
        try:
            super().run()
        finally:
            self._package.hw.uv_led.off()
            self._package.hw.stop_fans()
            self._uv_meter.close()
