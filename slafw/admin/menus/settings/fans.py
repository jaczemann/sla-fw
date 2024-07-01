# This file is part of the SLA firmware
# Copyright (C) 2020-2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Dict, Callable
from threading import Thread
from functools import partial
from time import sleep

from slafw.libPrinter import Printer
from slafw.hardware.fan import Fan
from slafw.admin.control import AdminControl
from slafw.admin.items import AdminIntValue, AdminBoolValue, AdminLabel
from slafw.admin.menus.settings.base import SettingsMenu


class FansMenu(SettingsMenu):
    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control, printer)
        self._fans = printer.hw.fans
        self._data: Dict[int, dict] = {}
        items = []
        for idx, fan in self._fans.items():
            self._data[idx] = {}
            enabled = AdminBoolValue.from_value(
                    f"{fan.name} fan enabled",
                    fan,
                    "enabled",
                    "fan_color")
            enabled.changed.connect(self._get_callback(self._changed_enable, idx))
            self._data[idx]["en"] = enabled
            items.append(enabled)

            if fan.has_auto_control:
                ac = AdminBoolValue.from_value(
                        f"{fan.name} fan auto control",
                        fan,
                        "auto_control",
                        "firmware-icon",
                        enabled=fan.enabled)
                ac.changed.connect(self._get_callback(self._changed_auto_control, idx))
                self._data[idx]["ac"] = ac
                items.append(ac)

            trpm = AdminIntValue(
                    f"{fan.name} fan target RPM",
                    partial(Fan.default_rpm.fget, fan), # type: ignore[attr-defined]
                    partial(Fan.default_rpm.fset, fan), # type: ignore[attr-defined]
                    100,
                    "limit_color",
                    enabled=fan.enabled and not fan.auto_control,
                    minimum=fan.min_rpm,
                    maximum=fan.max_rpm)
            self._data[idx]["trpm"] = trpm
            items.append(trpm)

            run = AdminBoolValue.from_value(
                    f"{fan.name} fan running",
                    fan,
                    "running",
                    "turn_off_color",
                    enabled=fan.enabled)
            self._data[idx]["run"] = run
            items.append(run)

            arpm = AdminLabel(None, "limit_color", enabled=fan.enabled)
            self._data[idx]["arpm"] = arpm
            items.append(arpm)

        self.add_items(items)
        self._running = True
        self._thread = Thread(target=self._run)

    def on_enter(self):
        self._thread.start()

    def on_leave(self):
        self._running = False
        self._thread.join()
        for fan in self._fans.values():
            fan.save(self._temp)
        super().on_leave()

    @staticmethod
    def _get_callback(callback: Callable, idx: int):
        return lambda: callback(idx)

    def _changed_enable(self, idx: int):
        if "ac" in self._data[idx]:
            self._data[idx]["ac"].enabled = self._fans[idx].enabled
        else:
            self._changed_auto_control(idx)
        self._data[idx]["run"].enabled = self._fans[idx].enabled
        self._data[idx]["arpm"].enabled = self._fans[idx].enabled

    def _changed_auto_control(self, idx: int):
        self._data[idx]["trpm"].enabled = self._fans[idx].enabled and not self._fans[idx].auto_control

    def _run(self):
        loop = 0
        while self._running:
            loop += 1
            if loop >= 10:
                for idx, fan in self._fans.items():
                    self._data[idx]["arpm"].set(f"{fan.name} fan actual RPM: {fan.rpm}")
                    loop = 0
            sleep(.1)
