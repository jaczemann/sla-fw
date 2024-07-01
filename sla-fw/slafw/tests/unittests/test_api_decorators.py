# This file is part of the SLA firmware
# Copyright (C) 2020 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import unittest
from typing import List, Dict, Any, Tuple
from unittest import TestCase
from gi.repository.GLib import Variant

from slafw.api.decorators import (
    wrap_dict_data,
    python_to_dbus_type,
    auto_dbus,
    gen_method_dbus_args_spec,
    auto_dbus_signal,
)


class TestWrapDictData(TestCase):
    def test_dict_str_int(self):
        self.assertEqual(
            {"num": Variant("i", 5), "str": Variant("s", "text")}, wrap_dict_data({"num": 5, "str": "text",})
        )

    def test_warnings(self):
        self.assertEqual(
            {"changes": Variant("a{sv}", {"exposure": Variant("(ii)", (10, 9))})},
            wrap_dict_data({"changes": {"exposure": (10, 9)}}),
        )

    def test_constraints(self):
        self.assertEqual(
            {"value": Variant("a{sv}", {"min": Variant("i", 5), "max": Variant("i", 10)})},
            wrap_dict_data({"value": {"min": 5, "max": 10}}),
        )


class TestPythonToDbus(TestCase):
    def test_int(self):
        self.assertEqual("i", python_to_dbus_type(int))

    def test_float(self):
        self.assertEqual("d", python_to_dbus_type(float))

    def test_bool(self):
        self.assertEqual("b", python_to_dbus_type(bool))

    def test_string(self):
        self.assertEqual("s", python_to_dbus_type(str))

    def test_array_string(self):
        self.assertEqual("as", python_to_dbus_type(List[str]))

    def test_list_list_int(self):
        self.assertEqual("aai", python_to_dbus_type(List[List[int]]))

    def test_dict_int_int(self):
        self.assertEqual("a{ii}", python_to_dbus_type(Dict[int, int]))

    def test_dict_str_dict_int_int(self):
        self.assertEqual("a{sa{si}}", python_to_dbus_type(Dict[str, Dict[str, int]]))

    def test_tuple_int_str_int(self):
        self.assertEqual("(isi)", python_to_dbus_type(Tuple[int, str, int]))

    def test_rauc_status(self):
        self.assertEqual("a(sa{sv})", python_to_dbus_type(List[Tuple[str, Dict[str, Any]]]))

    def test_dict_str_dict_str_any(self):
        self.assertEqual("a{sa{sv}}", python_to_dbus_type(Dict[str, Dict[str, Any]]))


class TestAutoDbus(TestCase):
    def test_simple(self):
        # No args
        def test1():
            pass

        self.assertEqual("<method name='test1'></method>", auto_dbus(test1).__dbus__)

    def test_arg(self):
        # Single arg
        def test2(a: str):
            # pylint: disable = unused-argument
            pass

        self.assertEqual(
            "<method name='test2'><arg type='s' name='a' direction='in'/></method>", auto_dbus(test2).__dbus__
        )

    def test_two_args(self):
        # Two args
        def test3(a: str, b: int):
            # pylint: disable = unused-argument
            pass

        self.assertEqual(
            "<method name='test3'><arg type='s' name='a' direction='in'/>"
            "<arg type='i' name='b' direction='in'/></method>",
            auto_dbus(test3).__dbus__,
        )

    def test_return(self):
        # Return
        def test4() -> float:
            return 1.23

        self.assertEqual(
            "<method name='test4'><arg type='d' name='return' direction='out'/></method>", auto_dbus(test4).__dbus__
        )

    def test_two_args_return(self):
        # Two args + Return
        def test5(a: str, b: int) -> float:
            # pylint: disable = unused-argument
            pass

        self.assertEqual(
            "<method name='test5'><arg type='s' name='a' direction='in'/>"
            "<arg type='i' name='b' direction='in'/><arg type='d' name='return' direction='out'/></method>",
            auto_dbus(test5).__dbus__,
        )


class TestDBusArgsGen(TestCase):
    def test_no_args(self):
        def simple():
            pass

        self.assertListEqual([], gen_method_dbus_args_spec(simple))

    def test_single_arg(self):
        def single(a: str):
            # pylint: disable = unused-argument
            pass

        self.assertListEqual(["<arg type='s' name='a' direction='in'/>"], gen_method_dbus_args_spec(single))

    def test_two_args(self):
        def two(a: str, b: int):
            # pylint: disable = unused-argument
            pass

        self.assertListEqual(
            ["<arg type='s' name='a' direction='in'/>", "<arg type='i' name='b' direction='in'/>"],
            gen_method_dbus_args_spec(two),
        )


class TestAutoDBusSignal(TestCase):
    def test_simple(self):
        def simple():
            pass

        self.assertEqual('<signal name="simple"></signal>', auto_dbus_signal(simple).__dbus__)

    def test_args(self):
        def args(a: str, b: int):
            # pylint: disable = unused-argument
            pass

        self.assertEqual(
            "<signal name=\"args\"><arg type='s' name='a' direction='out'/>"
            "<arg type='i' name='b' direction='out'/></signal>",
            auto_dbus_signal(args).__dbus__,
        )


if __name__ == "__main__":
    unittest.main()
