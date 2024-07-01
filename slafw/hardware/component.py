# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import logging


class HardwareComponent:
    """
    Abstract base for HW component
    """

    def __init__(self, name: str):
        self._name = name
        self._logger = logging.getLogger(f"{self.__class__.__name__}({name})")

    @property
    def name(self) -> str:
        return self._name

    async def run(self):
        """
        Component run

        Override this one to enable async service for the hw component
        """
