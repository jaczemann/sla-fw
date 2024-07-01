# This file is part of the SLA firmware
# Copyright (C) 2020-2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from threading import Thread, current_thread
from typing import Callable

from slafw.admin.control import AdminControl
from slafw.admin.items import AdminLabel, AdminAction
from slafw.admin.menu import AdminMenu


class Confirm(AdminMenu):
    def __init__(self, control: AdminControl, target: Callable[[], None], headline="Confirm", text=""):
        super().__init__(control)
        self._target = target
        self._headline = self.add_label(f"<b>{headline}</b>", "confirm_small_white")
        if text:
            self._text = self.add_label(text, "confirm_small_white")
        self.add_back(bold=False)
        self.add_item(AdminAction("<b>Continue</b>", self.cont, "yes_green"))

    def cont(self):
        self._control.pop()
        self._target()


class Error(AdminMenu):
    def __init__(self, control: AdminControl, headline="Error", text="", pop=2):
        super().__init__(control)
        self._headline = self.add_label(f"<b>{headline}</b>", "error_small_white")
        if text:
            self._text = self.add_label(text, "error_small_white")
        self._pop_num = pop
        self.add_item(AdminAction("Ok", self.ok, "yes_green"))

    def ok(self):
        self._control.pop(self._pop_num)


class Info(AdminMenu):
    def __init__(self, control: AdminControl, text: str, headline="Info", pop=1):
        super().__init__(control)
        self._headline = self.add_label(f"<b>{headline}</b>", "info_off_small_white")
        self._text = self.add_label(text, "info_off_small_white")
        self._pop_num = pop
        self.add_item(AdminAction("Ok", self.ok, "yes_green"))

    def ok(self):
        self._control.pop(self._pop_num)


class Wait(AdminMenu):
    def __init__(self, control: AdminControl, body: Callable[[AdminLabel], None], pop=1):
        super().__init__(control)
        self._body = body
        self._thread = Thread(target=self._run)
        self.headline = self.add_label("<b>Wait...</b>", "sandclock_color")
        self.status = self.add_label(None, "sandclock_color")
        self._num_pop = pop

    def on_enter(self):
        self._thread.start()

    def on_leave(self):
        if current_thread() != self._thread:
            self._thread.join()

    def _run(self):
        self._body(self.status)
        self._control.pop(self._num_pop, self)
