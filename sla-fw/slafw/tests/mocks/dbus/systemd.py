# This file is part of the SLA firmware
# Copyright (C) 2021 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from pydbus.generic import signal

from slafw.api.decorators import dbus_api, auto_dbus


@dbus_api
class Systemd:
    # pylint: disable = too-few-public-methods
    # pylint: disable = no-self-use
    __INTERFACE__ = "org.freedesktop.systemd1"

    PropertiesChanged = signal()

    def __init__(self):
        pass

    @auto_dbus
    def StopUnit(self, _: str, __: str) -> None:
        return None
