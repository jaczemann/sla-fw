# This file is part of the SLA firmware
# Copyright (C) 2021 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

# pylint: disable = unused-argument, no-self-use

from typing import Dict, Any

from pydbus.generic import signal
from pydbus import Variant

from slafw.api.decorators import dbus_api, auto_dbus, auto_dbus_signal

# TODO replace for real file manager

@dbus_api
class FileManager0:
    """Dbus mock api for share file system data"""

    __INTERFACE__ = "cz.prusa3d.sl1.filemanager0"

    PropertiesChanged = signal()

    @auto_dbus_signal
    def MediaInserted(self, path: str):
        pass

    @auto_dbus_signal
    def MediaEjected(self, root_path: str):
        pass

    @auto_dbus
    def remove(self, path: str) -> None:
        pass

    @auto_dbus
    def get_metadata(self, path: str, thumbnail: bool) -> Dict[str, Any]:
        return {
            "files": Variant("a{sv}", {
                "mtime": Variant("i", 1321321),
                "origin": Variant("s", "local"),
                "size": Variant("i", 1231321),
            })
        }

    @auto_dbus
    def get_all(self, maxdepth: int) -> Dict[str, Any]:
        return Variant("a{sv}", {})
