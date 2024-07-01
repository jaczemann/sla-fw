# This file is part of the SLA firmware
# Copyright (C) 2020-2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import Dict, Any

from slafw.wizard.data_package import WizardDataPackage
from slafw.wizard.actions import UserActionBroker
from slafw.wizard.checks.base import WizardCheckType, DangerousCheck
from slafw.wizard.setup import Configuration, Resource


class UVLEDsTest(DangerousCheck):
    def __init__(self, package: WizardDataPackage):
        super().__init__(package, WizardCheckType.UV_LEDS, Configuration(None, None), [Resource.UV])
        self._result_data: Dict[str, Any] = {}

    async def async_task_run(self, actions: UserActionBroker):
        await self.wait_cover_closed()
        self._result_data = await self._package.hw.uv_led.selftest(self._progress_update)

    def _progress_update(self, progress: float):
        self.progress = progress

    def get_result_data(self) -> Dict[str, Any]:
        return self._result_data
