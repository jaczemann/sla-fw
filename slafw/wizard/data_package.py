# This file is part of the SLA firmware
# Copyright (C) 2022-2024 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Any
from dataclasses import dataclass, field, make_dataclass
import weakref

from slafw.hardware.hardware import BaseHardware
from slafw.configs.writer import ConfigWriter
from slafw.configs.runtime import RuntimeConfig
from slafw.image.exposure_image import ExposureImage


@dataclass
class WizardDataPackage:
    """
    Data getting passed to the wizards, wizard groups and wizard checks for their initialization
    """
    hw: BaseHardware = None
    config_writers: Any = None
    runtime_config: RuntimeConfig = None
    exposure_image: ExposureImage = None


def fill_wizard_data_package(printer) -> WizardDataPackage:
    return WizardDataPackage(
        hw=printer.hw,
        config_writers=make_config_writers(printer.hw.config),
        runtime_config=printer.runtime_config,
        exposure_image=weakref.proxy(printer.exposure_image)
    )


def make_config_writers(hw_config: ConfigWriter) -> Any:
    cw_items = [("hw_config", ConfigWriter, field(default=hw_config.get_writer(), init=False))]
    return make_dataclass("ConfigWriters", cw_items)()
