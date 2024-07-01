# This file is part of the SLA firmware
# Copyright (C) 2021 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import functools
from typing import Callable

from slafw.admin.menu import AdminMenu
from slafw.admin.menus.dialogs import Error


class SafeAdminMenu(AdminMenu):
    SAFE_CALL_ATTR_NAME = "__admin_safe_call__"

    @staticmethod
    def safe_call(method: Callable[[], None]):
        setattr(method, SafeAdminMenu.SAFE_CALL_ATTR_NAME, True)
        return method

    def __getattribute__(self, item: str):
        obj = object.__getattribute__(self, item)
        if hasattr(obj, SafeAdminMenu.SAFE_CALL_ATTR_NAME):

            @functools.wraps(obj)
            def wrap(*args, **kwargs):
                try:
                    obj(*args, **kwargs)
                except Exception as exception:
                    text = f"{type(exception).__name__}\n{Exception.__str__(exception)}"
                    self._control.enter(
                        Error(self._control, text=text, headline="Failed to execute admin action", pop=1)
                    )
                    raise

            return wrap

        return obj
