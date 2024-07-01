# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from pydbus.generic import signal

from slafw.api.decorators import dbus_api, auto_dbus


@dbus_api
class TimeDate:
    __INTERFACE__ = "org.freedesktop.timedate1"
    DEFAULT_TZ = 'America/Vancouver'
    DEFAULT_NTP = True

    PropertiesChanged = signal()

    def __init__(self):
        self._ntp = TimeDate.DEFAULT_NTP
        self._tz = TimeDate.DEFAULT_TZ

    def is_default_tz(self) -> bool:
        return self._tz == TimeDate.DEFAULT_TZ

    def is_default_ntp(self) -> bool:
        return self._ntp == TimeDate.DEFAULT_NTP

    @auto_dbus
    @property
    def Timezone(self) -> str:
        return self._tz

    @auto_dbus
    def SetTimezone(self, tz: str, _: bool):
        self._tz = tz

    @auto_dbus
    @property
    def NTP(self) -> bool:
        return self._ntp

    @auto_dbus
    def SetNTP(self, state: bool, _: bool) -> None:
        self._ntp = state
