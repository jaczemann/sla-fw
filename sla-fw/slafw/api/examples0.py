# This file is part of the SLA firmware
# Copyright (C) 2020 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from typing import Any

from pydbus.generic import signal

from slafw.api.decorators import dbus_api, auto_dbus
from slafw.state_actions.examples import Examples


@dbus_api
class Examples0:
    __INTERFACE__ = "cz.prusa3d.sl1.examples0"
    DBUS_PATH = "/cz/prusa3d/sl1/examples0"

    PropertiesChanged = signal()

    def __init__(self, examples: Examples):
        self.logger = logging.getLogger(__name__)
        self._examples = examples
        examples.change.connect(self._handle_change)

    @auto_dbus
    @property
    def state(self) -> int:
        return self._examples.state.value

    @auto_dbus
    @property
    def download_progress(self) -> float:
        return self._examples.download_progress

    @auto_dbus
    @property
    def unpack_progress(self) -> float:
        return self._examples.unpack_progress

    @auto_dbus
    @property
    def copy_progress(self) -> float:
        return self._examples.copy_progress

    def _handle_change(self, key: str, _: Any):
        if key in self._CHANGE_MAP:
            for changed in self._CHANGE_MAP[key]:
                self.PropertiesChanged(self.__INTERFACE__, {changed: getattr(self, changed)}, [])

    _CHANGE_MAP = {
        "state": {"state"},
        "download_progress": {"download_progress"},
        "unpack_progress": {"unpack_progress"},
        "copy_progress": {"copy_progress"},
    }
