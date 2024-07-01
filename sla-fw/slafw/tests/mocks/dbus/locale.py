# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import List

from pydbus.generic import signal

from slafw.api.decorators import dbus_api, auto_dbus


@dbus_api
class Locale:
    __INTERFACE__ = "org.freedesktop.locale1"
    DEFAULT_LOCALE = ["C"]

    PropertiesChanged = signal()

    def __init__(self):
        self._locale = Locale.DEFAULT_LOCALE

    @auto_dbus
    @property
    def Locale(self) -> List[str]:
        return self._locale

    @auto_dbus
    def SetLocale(self, locale: List[str], _: bool) -> None:
        self._locale = locale

    def is_default(self):
        return self._locale == Locale.DEFAULT_LOCALE
