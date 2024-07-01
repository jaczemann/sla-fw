# This file is part of the SLA firmware
# Copyright (C) 2020 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from collections import defaultdict

from PySignal import Signal


class TraceableDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.changed = Signal()

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.changed.emit()


class TraceableDefaultDict(defaultdict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.changed = Signal()

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.changed.emit()


class TraceableList(list):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.changed = Signal()

    def append(self, obj) -> None:
        super().append(obj)
        self.changed.emit()

    def remove(self, obj) -> None:
        super().remove(obj)
        self.changed.emit()
