# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from slafw.functions.system import set_configured_printer_model, set_factory_uvpwm
from slafw.hardware.printer_model import PrinterModel
from slafw.wizard.data_package import WizardDataPackage
from slafw.wizard.actions import UserActionBroker
from slafw.wizard.checks.base import Check, WizardCheckType


class ResetUVPWM(Check):
    def __init__(self, package: WizardDataPackage):
        super().__init__(WizardCheckType.ERASE_UV_PWM)
        self._package = package

    async def async_task_run(self, actions: UserActionBroker):
        del self._package.config_writers.hw_config.uvCurrent
        del self._package.config_writers.hw_config.uvPwmTune
        pwm = self._package.hw.uv_led.parameters.safe_default_pwm
        self._package.config_writers.hw_config.uvPwm = pwm
        set_factory_uvpwm(pwm)


class ResetSelfTest(Check):
    def __init__(self, package: WizardDataPackage):
        super().__init__(WizardCheckType.RESET_SELF_TEST)
        self._package = package

    async def async_task_run(self, actions: UserActionBroker):
        self._package.config_writers.hw_config.showWizard = True


class ResetMechanicalCalibration(Check):
    def __init__(self, package: WizardDataPackage):
        super().__init__(WizardCheckType.RESET_MECHANICAL_CALIBRATION)
        self._package = package

    async def async_task_run(self, actions: UserActionBroker):
        del self._package.config_writers.hw_config.tower_height_nm
        del self._package.config_writers.hw_config.towerHeight
        del self._package.config_writers.hw_config.tiltHeight
        self._package.config_writers.hw_config.calibrated = False


class ResetHwCounters(Check):
    def __init__(self, package: WizardDataPackage):
        super().__init__(WizardCheckType.RESET_HW_COUNTERS)
        self._package = package

    async def async_task_run(self, actions: UserActionBroker):
        self._package.hw.uv_led.clear_usage()
        self._package.hw.exposure_screen.clear_usage()


class MarkPrinterModel(Check):
    def __init__(self, package: WizardDataPackage, model: PrinterModel):
        super().__init__(WizardCheckType.MARK_PRINTER_MODEL)
        self._package = package
        self._model = model

    async def async_task_run(self, actions: UserActionBroker):
        self._logger.info("Setting printer model to %s", self._model)
        set_configured_printer_model(self._model)
        self._package.config_writers.hw_config.vatRevision = self._model.options.vat_revision  # type: ignore[attr-defined]
