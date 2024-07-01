# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from dataclasses import dataclass


@dataclass(eq=False)
class PrinterOptions:
    has_tilt: bool
    has_booster: bool
    vat_revision: int
    has_UV_calibration: bool
    has_UV_calculation: bool
