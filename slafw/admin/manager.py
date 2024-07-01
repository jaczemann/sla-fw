# This file is part of the SLA firmware
# Copyright (C) 2020 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
from collections import deque
from typing import Deque, Optional

from PySignal import Signal

from slafw.admin.base_menu import AdminMenuBase
from slafw.admin.control import AdminControl
from slafw.admin.menu import AdminMenu


class AdminManager(AdminControl):
    # pylint: disable=too-many-instance-attributes
    def __init__(self):
        self._logger = logging.getLogger(__name__)
        self._menus: Deque[AdminMenu] = deque()
        self.menu_changed = Signal()
        self.enter_sysinfo = Signal()
        self.enter_touchscreen_test = Signal()
        self.enter_fullscreen_image = Signal()
        self.enter_tower_moves = Signal()
        self.enter_tilt_moves = Signal()

    @property
    def current_menu(self) -> Optional[AdminMenu]:
        if self._menus:
            return self._menus[-1]
        return None

    def enter(self, menu: AdminMenuBase) -> None:
        self._logger.info("Entering admin menu: %s", menu)
        self._menus.append(menu)
        self.menu_changed.emit()
        menu.on_enter()

    def exit(self) -> None:
        self.pop(len(self._menus))

    def pop(self, count=1, poping_menu: Optional[AdminMenuBase] = None) -> None:
        current_menu = self.current_menu
        if poping_menu and current_menu != poping_menu:
            self._logger.info("Not poping non-active menu.")
            return
        for _ in range(count):
            left = self._menus.pop()
            self._logger.info("Levaing admin menu: %s", left)
            left.on_leave()
        if current_menu:
            current_menu.on_reenter()
        self.menu_changed.emit()

    def root(self) -> None:
        self.pop(len(self._menus) - 1)

    def sysinfo(self):
        self.enter_sysinfo.emit()

    def touchscreen_test(self):
        self.enter_touchscreen_test.emit()

    def fullscreen_image(self):
        self.enter_fullscreen_image.emit()

    def tower_moves(self):
        self.enter_tower_moves.emit()

    def tilt_moves(self):
        self.enter_tilt_moves.emit()
