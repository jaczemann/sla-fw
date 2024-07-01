# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2020-2021 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
from PySignal import Signal
from slafw.logger_config import set_log_level


class RuntimeConfig:
    # pylint: disable=too-many-instance-attributes
    """
    Runtime printer configuration
    """

    def __init__(self):
        self._logger = logging.getLogger(__name__)
        self.show_admin_changed = Signal()
        self._show_admin: bool = False
        self.factory_mode_changed = Signal()
        self._factory_mode: bool = False

    @property
    def show_admin(self) -> bool:
        return self._show_admin

    @show_admin.setter
    def show_admin(self, value: bool):
        if self._show_admin != value:
            self._show_admin = value
            self.show_admin_changed.emit(value)
        if value:
            self._logger.info("Setting loglevel to DEBUG (transient)")
            try:
                set_log_level(level=logging.DEBUG, name="slafw", persistent=False)
            except Exception:
                self._logger.exception("Failed to set loglevel")

    @property
    def factory_mode(self) -> bool:
        return self._factory_mode

    @factory_mode.setter
    def factory_mode(self, value: bool):
        if self._factory_mode != value:
            self._factory_mode = value
            self.factory_mode_changed.emit(value)
