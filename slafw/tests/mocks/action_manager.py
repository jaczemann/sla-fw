# This file is part of the SLA firmware
# Copyright (C) 2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from PySignal import Signal


class ActionManager:
    # pylint: disable = too-few-public-methods
    # pylint: disable = too-many-instance-attributes
    def __init__(self, exposure):
        self.exposure_change = Signal()
        self.exposure = exposure
