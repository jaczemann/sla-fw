# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import operator
import unittest
from pathlib import Path
from shutil import copyfile
from unittest.mock import Mock, MagicMock

from slafw import defines
from slafw.configs.hw import HwConfig
from slafw.configs.unit import Nm, Ustep
from slafw.configs.ini import IniConfig
from slafw.configs.project import ProjectConfig
from slafw.configs.value import FloatValue, IntListValue, IntValue, BoolValue, FloatListValue, TextValue
from slafw.configs.writer import ConfigWriter
from slafw.tests.base import SlafwTestCase


class TestConfigValues(SlafwTestCase):
    def test_int(self):
        class IntConfig(IniConfig):
            a = IntValue(4)
            b = IntValue(8, minimum=5, maximum=10)
            c = IntValue(-5, minimum=-10, maximum=1)
            ab = IntValue(lambda s: s.a * s.b)

        c = IntConfig()

        self.assertEqual(4, c.a)
        self.assertEqual(8, c.b)
        self.assertEqual(-5, c.c)
        self.assertEqual(c.a * c.b, c.ab)
        c.read_text(
            """
        a = 55
        b = 11
        c = -1
        """
        )
        self.assertEqual(55, c.a)
        self.assertEqual(10, c.b)
        self.assertEqual(-1, c.c)
        self.assertEqual(c.a * c.b, c.ab)
        c.a = 30
        c.b = 5
        c.c = -4
        self.assertEqual(30, c.a)
        self.assertEqual(5, c.b)
        self.assertEqual(-4, c.c)
        self.assertEqual(c.a * c.b, c.ab)

    def test_float(self):
        class FloatConfig(IniConfig):
            a = FloatValue(4)
            b = FloatValue(8, minimum=5, maximum=10.1)
            c = FloatValue(-5, minimum=-10, maximum=1)
            ab = FloatValue(lambda s: s.a * s.b)

        c = FloatConfig()

        self.assertEqual(4, c.a)
        self.assertEqual(8, c.b)
        self.assertEqual(-5, c.c)
        self.assertEqual(c.a * c.b, c.ab)
        c.read_text(
            """
        a = 5.5
        b = 11
        c = -1
        """
        )
        self.assertEqual(5.5, c.a)
        self.assertEqual(10.1, c.b)
        self.assertEqual(-1, c.c)
        self.assertEqual(c.a * c.b, c.ab)
        c.a = 123.456
        c.b = 10.1
        c.c = -4.44
        self.assertEqual(123.456, c.a)
        self.assertEqual(10.1, c.b)
        self.assertEqual(-4.44, c.c)
        self.assertEqual(c.a * c.b, c.ab)

    def test_bool(self):
        class BoolConfig(IniConfig):
            a = BoolValue(False)
            b = BoolValue(True)
            t0 = BoolValue(True)
            t1 = BoolValue(True)
            t2 = BoolValue(True)
            f0 = BoolValue(False)
            f1 = BoolValue(False)
            f2 = BoolValue(False)

        c = BoolConfig()
        self.assertFalse(c.a)
        self.assertTrue(c.b)
        c.read_text(
            """
        f0 = true
        f1 = yes
        f2 = on
        t0 = false
        t1 = no
        t2 = off
        """
        )
        self.assertTrue(c.f0)
        self.assertTrue(c.f1)
        self.assertTrue(c.f2)
        self.assertFalse(c.t0)
        self.assertFalse(c.t1)
        self.assertFalse(c.t2)

    def test_string(self):
        class StringConfig(IniConfig):
            a = TextValue("def")
            b = TextValue()
            c = TextValue()

        c = StringConfig()
        self.assertEqual("def", c.a)
        self.assertEqual("", c.b)
        c.read_text(
            """
        a = old school text
        b = "toml compatible text"
        c = 123 numbers test 123"""
        )
        self.assertEqual("old school text", c.a)
        self.assertEqual("toml compatible text", c.b)
        self.assertEqual("123 numbers test 123", c.c)

    def test_lists(self):
        class ListConfig(IniConfig):
            i0 = IntListValue([1, 2, 3], length=3)
            i1 = IntListValue([1, 2, 3], length=3)
            f0 = FloatListValue([0.1, 0.2, 0.3], length=3)
            f1 = FloatListValue([0.1, 0.2, 0.3], length=3)
            i2 = IntListValue([0, 0, 0], length=3)

        c = ListConfig()
        self.assertEqual([1, 2, 3], c.i0)
        self.assertEqual([1, 2, 3], c.i1)
        self.assertEqual([0.1, 0.2, 0.3], c.f0)
        self.assertEqual([0.1, 0.2, 0.3], c.f1)

        c.read_text(
            """
        i0 = [ 1, 1, 1 ]
        i1 = 1 1 1
        f0 = [0.1, 0.1,0.1]
        f1 = 0.1    0.1 0.1
        i2 = [ 12840, 14115, 15640,]
        """
        )
        self.assertEqual([1, 1, 1], c.i0)
        self.assertEqual([1, 1, 1], c.i1)
        self.assertEqual([0.1, 0.1, 0.1], c.f0)
        self.assertEqual([0.1, 0.1, 0.1], c.f1)
        self.assertEqual([12840, 14115, 15640], c.i2)

    def test_dictionary(self):
        class SimpleConfig(IniConfig):
            a = IntValue(5)

        s = SimpleConfig()
        self.assertIn("a", s.as_dictionary())
        self.assertEqual(5, s.as_dictionary()["a"])
        self.assertNotIn("a", s.as_dictionary(nondefault=False))
        s.read_text("a = 5")  # Setting value to default should not make it non-default
        self.assertNotIn("a", s.as_dictionary(nondefault=False))

    def test_value_reset(self):
        class SimpleConfig(IniConfig):
            a = IntValue(5)

        s = SimpleConfig()
        self.assertEqual(5, s.a)
        s.a = 7
        self.assertEqual(7, s.a)
        s.factory_reset()
        self.assertEqual(5, s.a)

    def test_alternated(self):
        class SimpleConfig(IniConfig):
            a = IntValue(5, minimum=4, maximum=6)

        # No alternated values
        s = SimpleConfig()
        s.read_text("a = 4")
        self.assertEqual(4, s.a)
        self.assertEqual({}, s.get_altered_values())

        # Alternated value a
        s.read_text("a = 10")
        self.assertEqual(6, s.a)
        self.assertEqual({"a": (6, 10)}, s.get_altered_values())


class TestHardwareConfig(SlafwTestCase):
    def __init__(self, *args, **kwargs):
        self.test_config_path = Path("hwconfig.test")
        self.writetest_config_path = Path("hwconfig.writetest")
        super().__init__(*args, **kwargs)

    def setUp(self):
        super().setUp()
        defines.hwConfigPathFactory = self.SAMPLES_DIR / "hardware.toml"
        defines.hwConfigPath = self.SAMPLES_DIR / "hardware-toml.cfg"
        copyfile(defines.hwConfigPath, "hwconfig.test")

    def tearDown(self):
        for path in [self.test_config_path, self.writetest_config_path]:
            if path.exists():
                path.unlink()
        super().tearDown()

    def test_read(self):
        hw_config = HwConfig(Path(defines.hwConfigPath))
        hw_config.read_file()

        self.assertFalse(hw_config.showUnboxing, "Test show unboxing read")
        self.assertTrue(hw_config.coverCheck, "Test cover check read")
        self.assertFalse(hw_config.calibrated, "Test calibrated read")
        self.assertEqual(hw_config.up_and_down_z_offset_nm, Nm(0), "Default Nm read")
        self.assertEqual(hw_config.tiltHeight, Ustep(2624), "Config Ustep read")

    @staticmethod
    def get_config_content(path: Path):
        return path.read_text(encoding="utf-8")

    def test_instances(self):
        """
        Ensure different instances do not share the data
        """
        a = HwConfig()
        a.showUnboxing = False
        HwConfig()
        self.assertFalse(a.showUnboxing)

    def test_write(self):
        hw_config = HwConfig(self.test_config_path, is_master=True)
        hw_config.tower_height_nm = Nm(-1)
        tower_height_nm = Nm(1024)
        hw_config.tower_height_nm = tower_height_nm

        self.assertEqual(hw_config.tower_height_nm, tower_height_nm, "Check tower height is set")

        hw_config.uvPwm = 222

        print(hw_config)
        hw_config.write(self.writetest_config_path)
        self.assertEqual('tower_height_nm = 1024\nuvPwm = 222\n', self.get_config_content(self.writetest_config_path),
                         "Check file lines append",)

        del hw_config.uvPwm
        hw_config.write(self.test_config_path)
        print(self.get_config_content(self.writetest_config_path))
        self.assertEqual('tower_height_nm = 1024\n', self.get_config_content(self.test_config_path),
                         "Check file lines delete",)

    def test_uvledpwm1(self):
        hw_config = HwConfig(self.SAMPLES_DIR / "hardware.cfg")
        hw_config.read_file()
        print(hw_config.uvPwm)
        self.assertEqual(0, hw_config.uvPwm, "UV LED PWM - No defaults at all")

    def test_uvledpwm2(self):
        hw_config = HwConfig(self.SAMPLES_DIR / "hardware-current.cfg")
        hw_config.read_file()
        self.assertEqual(152, hw_config.uvPwm, "UV LED PWM - current to PWM")

    def test_uvledpwm3(self):
        hw_config = HwConfig(self.SAMPLES_DIR / "hardware-pwm.cfg")
        hw_config.read_file()
        self.assertEqual(142, hw_config.uvPwm, "UV LED PWM - direct PWM")

    def test_uvledpwm4(self):
        hw_config = HwConfig(
            self.SAMPLES_DIR / "hardware.cfg", factory_file_path=self.SAMPLES_DIR / "hardware-current.toml"
        )
        hw_config.read_file()
        self.assertEqual(243, hw_config.uvPwm, "UV LED PWM - default current to PWM")

    def test_uvledpwm5(self):
        hw_config = HwConfig(
            self.SAMPLES_DIR / "hardware.cfg", factory_file_path=self.SAMPLES_DIR / "hardware-pwm.toml"
        )
        hw_config.read_file()
        self.assertEqual(123, hw_config.uvPwm, "UV LED PWM - default direct PWM")


class TestConfigHelper(SlafwTestCase):
    CONFIG_PATH = Path("config.cfg")

    def setUp(self):
        super().setUp()
        self.hw_config = HwConfig(self.CONFIG_PATH, is_master=True)
        self.helper = ConfigWriter(self.hw_config)

    def tearDown(self):
        if self.CONFIG_PATH.exists():
            self.CONFIG_PATH.unlink()
        super().tearDown()

    def test_boolValueStore(self):
        self.helper.autoOff = True
        self.helper.resinSensor = False

        self.assertTrue(self.helper.autoOff)
        self.assertFalse(self.helper.resinSensor)
        self.assertIsInstance(self.helper.autoOff, bool)
        self.assertIsInstance(self.helper.resinSensor, bool)

    def test_integerValueStore(self):
        self.helper.uvWarmUpTime = 42

        self.assertEqual(self.helper.uvWarmUpTime, 42)
        self.assertIsInstance(self.helper.uvWarmUpTime, int)

    def test_floatValueStore(self):
        self.helper.uvCurrent = 4.2

        self.assertAlmostEqual(self.helper.uvCurrent, 4.2)
        self.assertIsInstance(self.helper.uvCurrent, float)

    def test_commit(self):
        # Fresh helper is not changed
        self.assertFalse(self.helper.changed())
        self.assertFalse(self.helper.changed("autoOff"))
        self.assertFalse(self.helper.changed("uvCurrent"))

        self.helper.autoOff = False

        # Underling values is intact before commit
        self.assertTrue(self.hw_config.autoOff)

        # Changed behaviour before commit
        self.assertTrue(self.helper.changed())
        self.assertTrue(self.helper.changed("autoOff"))
        self.assertFalse(self.helper.changed("uvCurrent"))

        self.helper.commit()

        # Underling value is changed after commit
        self.assertFalse(self.hw_config.autoOff)

        # Changed behaviour after commit
        self.assertFalse(self.helper.changed())
        self.assertFalse(self.helper.changed("autoOff"))
        self.assertFalse(self.helper.changed("uvCurrent"))

    def test_changed(self):
        self.assertFalse(self.helper.changed(), "Fresh config is not changed")
        self.helper.autoOff = not self.helper.autoOff
        self.assertTrue(self.helper.changed(), "Modified config is changed")
        self.helper.autoOff = not self.helper.autoOff
        self.assertFalse(self.helper.changed(), "After modify revert the config is not changed")

    def test_empty_commit(self):
        self.hw_config.write = Mock()
        writer = ConfigWriter(self.hw_config)
        writer.commit()
        self.hw_config.write.assert_not_called()

    def test_on_change(self):
        on_change = MagicMock()
        on_change.__self__ = Mock(name="self")
        on_change.__func__ = Mock(name="func")
        on_change("calibrated", True)
        self.hw_config.add_onchange_handler(on_change)
        self.helper.calibrated = True
        self.helper.commit()
        on_change.assert_called_with("calibrated", True)

    def test_delete(self):
        default = self.hw_config.uvPwm
        self.hw_config.uvPwm = 123
        self.assertEqual(123, self.helper.uvPwm)
        self.assertEqual(123, self.hw_config.uvPwm)
        del self.helper.uvPwm
        self.assertEqual(default, self.helper.uvPwm)
        self.assertEqual(123, self.hw_config.uvPwm)
        self.helper.commit()
        self.assertEqual(default, self.hw_config.uvPwm)


class TestPrintConfig(SlafwTestCase):
    CONFIG_PATH = Path("config.cfg")

    def setUp(self):
        super().setUp()
        self.print_config = ProjectConfig()
        self.print_config.read_file(self.SAMPLES_DIR / "num_name_print_config.ini")

    def test_num_fade(self):
        self.assertEqual(10, self.print_config.fadeLayers)

    def test_material(self):
        self.assertEqual(19.292032, self.print_config.usedMaterial)

    def test_name(self):
        self.assertEqual("123456789", self.print_config.job_dir)


class TestUnit(SlafwTestCase):

    def setUp(self):
        super().setUp()
        self.a = Nm(2)
        self.b = self.a
        self.c = Nm(4)
        self.d = Ustep(0)
        self.e = 1

    def test_eq_neq(self):
        self.assertEqual(self.a, self.b)
        self.assertEqual(self.b, self.a)
        self.assertNotEqual(self.a, self.c)
        self.assertNotEqual(self.c, self.a)
        for op in (operator.eq, operator.ne):
            with self.assertRaises(TypeError):
                _ = op(self.a, self.d)
            with self.assertRaises(TypeError):
                _ = op(self.a, self.e)

    def test_gt_ge_lt_le(self):
        self.assertLess(self.a, self.c)
        self.assertLessEqual(self.a, self.a)
        self.assertGreater(self.c, self.a)
        self.assertGreaterEqual(self.a, self.a)
        for op in (operator.gt, operator.ge, operator.lt, operator.le):
            with self.assertRaises(TypeError):
                _ = op(self.a, self.d)
            with self.assertRaises(TypeError):
                _ = op(self.a, self.e)

    def test_add_sub(self):
        r = Nm(6)
        self.assertEqual(r, self.a + self.c)
        self.assertEqual(r, self.c + self.a)
        r = Nm(-2)
        self.assertEqual(r, self.a - self.c)
        self.assertEqual(self.a, self.c - self.a)
        for op in (operator.add, operator.sub):
            with self.assertRaises(TypeError):
                _ = op(self.a, self.d)
            with self.assertRaises(TypeError):
                _ = op(self.a, self.e)

    def test_mul_div(self):
        r = Nm(8)
        self.assertEqual(r, self.a * self.c)
        self.assertEqual(r, self.c * self.a)
        r = Nm(0)
        self.assertEqual(r, self.a / self.c)
        self.assertEqual(self.a, self.c / self.a)
        r = Nm(1)
        c = Nm(3)
        self.assertEqual(r, self.c // c)
        r = Nm(0)
        self.assertEqual(r, c // self.c)
        for op in (operator.mul, operator.truediv, operator.floordiv):
            with self.assertRaises(TypeError):
                _ = op(self.a, self.d)
            _ = op(self.a, self.e)

    def test_str_repr_int_abs_neg(self):
        self.assertEqual("2", str(self.a))
        self.assertEqual("2", repr(self.a))
        self.assertEqual(2, int(self.a))
        self.assertEqual(self.a, abs(self.a))
        a = Nm(-2)
        self.assertEqual(self.a, abs(a))
        self.assertEqual(self.a, -a)

if __name__ == "__main__":
    unittest.main()
