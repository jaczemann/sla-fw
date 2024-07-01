# This file is part of the SLA firmware
# Copyright (C) 2020-2021 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from abc import abstractmethod, ABC
from typing import Optional

from slafw.admin.base_menu import AdminMenuBase


class AdminControl(ABC):
    @abstractmethod
    def pop(self, count=1, poping_menu: Optional[AdminMenuBase] = None) -> None:
        """
        Return to previous admin menu
        """

    @abstractmethod
    def root(self) -> None:
        """
        Return to root admin menu
        """

    @abstractmethod
    def enter(self, menu: AdminMenuBase) -> None:
        """
        Enter admin menu

        :param menu: Admin menu to enter
        """

    @abstractmethod
    def exit(self) -> None:
        """
        Exit admin mode
        """

    @abstractmethod
    def sysinfo(self) -> None:
        """
        Enter user sysinfo
        """

    @abstractmethod
    def touchscreen_test(self) -> None:
        """
        Enter touchscreen test - implemented by touch UI
        """

    @abstractmethod
    def fullscreen_image(self) -> None:
        """
        Enter fullscreen image
        """

    @abstractmethod
    def tower_moves(self) -> None:
        """
        Enter manual tower moves
        """

    @abstractmethod
    def tilt_moves(self) -> None:
        """
        Enter manual tilt moves
        """
