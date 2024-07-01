# This file is part of the SLA firmware
# Copyright (C) 2020 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import unittest
from typing import Any
from unittest.mock import Mock

from slafw.admin.items import AdminIntValue, AdminAction, AdminValue
from slafw.admin.menu import AdminMenu


class SampleMenu(AdminMenu):
    def __init__(self):
        super().__init__(Mock())
        self._a = 42
        self.called = False

        self.add_item(AdminAction("print_hello", self.print_hello))
        self.add_item(AdminIntValue.from_property(self, SampleMenu.a, 1))

    def print_hello(self):
        print("Hello world")
        self.called = True

    @property
    def a(self) -> int:
        print(f"a > {self._a}")
        return self._a

    @a.setter
    def a(self, value: int) -> None:
        print(f"a < {value}")
        self._a = value

    def get_value(self, name: str) -> Any:
        item = self.items[name]
        if not isinstance(item, AdminValue):
            raise ValueError("Not a value")
        return item.get_value()

    def set_value(self, name: str, value: Any) -> None:
        item = self.items[name]
        if not isinstance(item, AdminValue):
            raise ValueError("Not a value")
        item.set_value(value)

    def execute_action(self, name: str):
        item = self.items[name]
        if not isinstance(item, AdminAction):
            raise ValueError("Not an action")
        item.execute()


class TestAdminMenu(unittest.TestCase):
    def test_items_list(self):
        m = SampleMenu()
        self.assertEqual(2, len(m.items))

    def test_value(self):
        m = SampleMenu()
        self.assertEqual(42, m.get_value("a"))
        m.set_value("a", 45)
        self.assertEqual(45, m.get_value("a"))

    def test_action(self):
        m = SampleMenu()
        m.execute_action("print_hello")
        self.assertTrue(m.called)

    def test_multiple_instances(self):
        m1 = SampleMenu()
        m2 = SampleMenu()

        m1.set_value("a", 100)
        m2.set_value("a", 101)
        self.assertEqual(100, m1.get_value("a"))
        self.assertEqual(101, m2.get_value("a"))

    def test_changed(self):
        m = SampleMenu()
        callback = Mock()
        # This lambda is important as mock doesn't work well without it.
        m.value_changed.connect(lambda: callback())  # pylint: disable=unnecessary-lambda
        m.get_value("a")
        self.assertFalse(callback.called)
        m.set_value("a", 123)
        self.assertTrue(callback.called)


if __name__ == "__main__":
    unittest.main()
