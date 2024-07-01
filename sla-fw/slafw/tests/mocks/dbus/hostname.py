# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from pydbus.generic import signal

from slafw.api.decorators import dbus_api, auto_dbus


@dbus_api
class Hostname:
    __INTERFACE__ = "org.freedesktop.hostname1"

    PropertiesChanged = signal()

    def __init__(self):
        self.hostname = ""
        self.static_hostname = ""

    @auto_dbus
    def SetStaticHostname(self, hostname: str, _: bool) -> None:
        self.static_hostname = hostname

    @auto_dbus
    def SetHostname(self, hostname: str, _: bool) -> None:
        self.hostname = hostname

    @auto_dbus
    @property
    def StaticHostname(self) -> str:
        return self.static_hostname

    @auto_dbus
    @property
    def Hostname(self) -> str:
        return self.hostname
