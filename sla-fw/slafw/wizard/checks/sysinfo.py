# This file is part of the SLA firmware
# Copyright (C) 2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional

from slafw.wizard.data_package import WizardDataPackage
from slafw.wizard.actions import UserActionBroker
from slafw.wizard.checks.base import Check, WizardCheckType
from slafw.wizard.setup import Configuration


@dataclass
class CheckData:
    # pylint: disable = too-many-instance-attributes
    # following values are for quality monitoring systems
    osVersion: str
    a64SerialNo: str
    mcSerialNo: str
    mcFwVersion: str
    mcBoardRev: str
    uvLedCounter_s: int
    displayCounter_s: int
    model: str


class SystemInfoTest(Check):
    def __init__(self, package: WizardDataPackage):
        super().__init__(WizardCheckType.SYS_INFO, Configuration(None, None), [])
        self._hw = package.hw
        self._result_data: Optional[CheckData] = None

    async def async_task_run(self, actions: UserActionBroker):
        self._logger.debug("Obtaining system information")

        self._result_data = CheckData(
            self._hw.system_version,
            self._hw.cpuSerialNo,
            self._hw.mcSerialNo,
            self._hw.mcFwVersion,
            self._hw.mcBoardRevision,
            self._hw.uv_led.usage_s,
            self._hw.exposure_screen.usage_s,
            self._hw.printer_model.name,  # type: ignore[attr-defined]
        )

    def get_result_data(self) -> Dict[str, Any]:
        return asdict(self._result_data)
