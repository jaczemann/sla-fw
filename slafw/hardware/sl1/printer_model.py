# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from abc import ABC

from slafw.hardware.printer_model import PrinterModelBase, PrinterModel
from slafw.hardware.printer_options import PrinterOptions


class PrinterModelSL1(PrinterModelBase):
    @property
    def name(self) -> str:
        return "SL1"

    @property
    def label_name(self) -> str:
        return "Original Prusa SL1"

    @property
    def value(self) -> int:
        return 1

    @property
    def options(self) -> PrinterOptions:
        return PrinterOptions(
            has_tilt=True,
            has_booster=False,
            vat_revision=0,
            has_UV_calibration=True,
            has_UV_calculation=False,
        )


class PrinterModelSL1SCommon(PrinterModelBase, ABC):
    @property
    def options(self) -> PrinterOptions:
        return PrinterOptions(
            has_tilt=True,
            has_booster=True,
            vat_revision=1,
            has_UV_calibration=False,
            has_UV_calculation=True,
        )


class PrinterModelSL1S(PrinterModelSL1SCommon):
    @property
    def name(self) -> str:
        return "SL1S"

    @property
    def label_name(self) -> str:
        return "Original Prusa SL1S SPEED"

    @property
    def value(self) -> int:
        return 2


class PrinterModelM1(PrinterModelSL1SCommon):
    @property
    def name(self):
        return "M1"

    @property
    def label_name(self) -> str:
        return "Original Prusa Medical One"

    @property
    def value(self) -> int:
        return 3


PrinterModel.register_model(PrinterModelSL1())
PrinterModel.register_model(PrinterModelSL1S())
PrinterModel.register_model(PrinterModelM1())
