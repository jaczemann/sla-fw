# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import unittest

from slafw.errors.errors import ConfigException
from slafw.tests.base import SlafwTestCase

from slafw.hardware.profiles import SingleProfile, ProfileSet
from slafw.hardware.sl1.tilt_profiles import MovingProfilesTiltSL1
from slafw.hardware.sl1.tower_profiles import MovingProfilesTowerSL1
from slafw.configs.value import IntValue, DictOfConfigs


class DummySingleProfile(SingleProfile):
    first_value = IntValue(888, minimum=0, maximum=999, factory=True)
    second_value = IntValue(777, minimum=0, maximum=999, factory=True)
    third_value = IntValue(666, minimum=0, maximum=999, factory=True)
    __definition_order__ = tuple(locals())

class ErrorSingleProfile(SingleProfile):
    first = IntValue(minimum=0, maximum=999, factory=True)
    __definition_order__ = tuple(locals())

class DummyProfileSet(ProfileSet):
    first_profile = DictOfConfigs(DummySingleProfile)
    second_profile = DictOfConfigs(DummySingleProfile)
    third_profile = DictOfConfigs(DummySingleProfile)
    __definition_order__ = tuple(locals())
    _add_dict_type = DummySingleProfile
    name = "test profile set"

class ErrorProfileSet1(ProfileSet):
    first_profile = DictOfConfigs(ErrorSingleProfile)
    second_profile = DictOfConfigs(ErrorSingleProfile)
    third_profile = DictOfConfigs(ErrorSingleProfile)
    __definition_order__ = tuple(locals())
    name = "test profile set"

class ErrorProfileSet2(ProfileSet):
    first = DictOfConfigs(DummySingleProfile)
    __definition_order__ = tuple(locals())
    name = "test profile set"

class TestProfileSet(SlafwTestCase):
    def setUp(self):
        super().setUp()
        self.infile = self.SAMPLES_DIR / "test_profile_set.json"
        self.outfile = self.TEMP_DIR / "test_out.json"

    def test_errors(self):
        with self.assertRaises(ConfigException):
            ErrorProfileSet1(self.infile)
        with self.assertRaises(ConfigException):
            ErrorProfileSet2(self.infile)

    def test_write_changed(self):
        test_profiles = DummyProfileSet(factory_file_path=self.outfile, default_file_path=self.infile)
        test_profiles.first_profile.first_value = 999
        test_profiles.write()
        with open(self.outfile, encoding="utf-8") as o:
            self.assertEqual({'first_profile': {'first_value': 999}}, json.load(o))

    def test_write_unchanged(self):
        test_profiles = DummyProfileSet(factory_file_path=self.outfile, default_file_path=self.infile)
        test_profiles.write()
        with open(self.outfile, encoding="utf-8") as o:
            self.assertFalse(len(json.load(o)))

    def test_writer(self):
        test_profiles = DummyProfileSet(factory_file_path=self.outfile, default_file_path=self.infile)
        writer = test_profiles.second_profile.get_writer()
        writer.second_value = 555
        writer.third_value = 999
        writer.commit()
        with open(self.outfile, encoding="utf-8") as o:
            self.assertEqual({'second_profile': {'second_value': 555, 'third_value': 999}}, json.load(o))

    def test_load_as_defaults(self):
        test_profiles = DummyProfileSet(factory_file_path=self.infile)
        fp = test_profiles.first_profile
        self.assertEqual(888, fp.get_values()["first_value"].get_default_value(fp))
        self.assertEqual(777, fp.get_values()["second_value"].get_default_value(fp))
        self.assertEqual(666, fp.get_values()["third_value"].get_default_value(fp))
        sp = test_profiles.second_profile
        self.assertEqual(888, sp.get_values()["first_value"].get_default_value(sp))
        tp = test_profiles.third_profile
        self.assertEqual(888, tp.get_values()["first_value"].get_default_value(tp))
        test_profiles = DummyProfileSet(default_file_path=self.infile)
        fp = test_profiles.first_profile
        self.assertEqual(1, fp.get_values()["first_value"].get_default_value(fp))
        self.assertEqual(2, fp.get_values()["second_value"].get_default_value(fp))
        self.assertEqual(3, fp.get_values()["third_value"].get_default_value(fp))
        sp = test_profiles.second_profile
        self.assertEqual(11, sp.get_values()["first_value"].get_default_value(sp))
        self.assertEqual(22, sp.get_values()["second_value"].get_default_value(sp))
        self.assertEqual(33, sp.get_values()["third_value"].get_default_value(sp))
        tp = test_profiles.third_profile
        self.assertEqual(111, tp.get_values()["first_value"].get_default_value(tp))
        self.assertEqual(222, tp.get_values()["second_value"].get_default_value(tp))
        self.assertEqual(333, tp.get_values()["third_value"].get_default_value(tp))

    def test_is_modified(self):
        test_profiles = DummyProfileSet(default_file_path=self.infile)
        self.assertFalse(test_profiles.first_profile.is_modified)
        test_profiles = DummyProfileSet(factory_file_path=self.infile)
        self.assertTrue(test_profiles.first_profile.is_modified)

    def test_factory_reset(self):
        test_profiles = DummyProfileSet(self.infile)
        test_profiles.factory_reset()
        self.assertEqual(888, test_profiles.first_profile.first_value)
        self.assertEqual(777, test_profiles.first_profile.second_value)
        self.assertEqual(666, test_profiles.first_profile.third_value)
        test_profiles.write(self.outfile)
        with open(self.outfile, encoding="utf-8") as o:
            self.assertEqual({}, json.load(o))
        test_profiles = DummyProfileSet(factory_file_path=self.infile)
        test_profiles.factory_reset(True)
        self.assertEqual(888, test_profiles.first_profile.first_value)
        self.assertEqual(777, test_profiles.first_profile.second_value)
        self.assertEqual(666, test_profiles.first_profile.third_value)
        test_profiles.write(self.outfile)
        with open(self.outfile, encoding="utf-8") as o:
            self.assertEqual({}, json.load(o))

    def test_add_from_file(self):
        # pylint: disable=no-member
        test_profiles = DummyProfileSet(default_file_path=self.infile)
        self.assertEqual(3, test_profiles.alpha.idx)
        self.assertEqual(4, test_profiles.bravo.idx)
        self.assertEqual(5, test_profiles.charlie.idx)
        self.assertEqual(444, test_profiles.alpha.first_value)
        self.assertEqual(555, test_profiles.alpha.second_value)
        self.assertEqual(666, test_profiles.alpha.third_value)
        self.assertEqual(44, test_profiles.bravo.first_value)
        self.assertEqual(55, test_profiles.bravo.second_value)
        self.assertEqual(66, test_profiles.bravo.third_value)
        self.assertEqual(4, test_profiles.charlie.first_value)
        self.assertEqual(5, test_profiles.charlie.second_value)
        self.assertEqual(6, test_profiles.charlie.third_value)

class TestMovingProfilesSL1(SlafwTestCase):
    def test_tilt_profiles(self):
        profiles = MovingProfilesTiltSL1(factory_file_path=self.DATA_DIR / "SL1" / "default_tilt_moving_profiles.json")
        # (start_steprate, max_steprate, accel, decel, current, stallguard_thr, coolstep_thr)
        assert_values = [
            (2560, 5120, 240, 240, 20, 7, 700),
            (1200, 1500, 160, 160, 16, 7, 1100),
            (100, 120, 10, 10, 11, 0, 1500),
            (200, 200, 0, 0, 44, 63, 0),
            (100, 300, 80, 80, 20, 0, 1500),
            (400, 400, 0, 0, 44, 63, 0),
            (300, 600, 150, 150, 20, 0, 1500),
            (400, 800, 150, 150, 20, 0, 1500),
            (500, 1000, 150, 150, 20, 0, 1500),
            (500, 1250, 150, 150, 20, 0, 1500),
            (1500, 1500, 0, 0, 44, 40, 2100),
            (1750, 1750, 0, 0, 44, 40, 2000),
            (1750, 2000, 150, 150, 44, 40, 2000),
            (1750, 2250, 150, 150, 44, 40, 2000),
            (3840, 5120, 80, 80, 16, 6, 1500),
            (8000, 8000, 0, 0, 26, 9, 700)
        ]
        for profile in profiles:
            self.assertEqual(assert_values[profile.idx], tuple(profile.dump()))

    def test_tower_profiles(self):
        profiles = MovingProfilesTowerSL1(factory_file_path=self.DATA_DIR / "SL1" / "default_tower_moving_profiles.json")
        # (start_steprate, max_steprate, accel, decel, current, stallguard_thr, coolstep_thr)
        assert_values = [
            (2500, 15000, 250, 150, 22, 4, 100),
            (2500, 7500, 250, 150, 16, 1, 500),
            (3200, 15000, 250, 250, 10, 3, 2200),
            (100, 150, 50, 50, 15, 0, 1500),
            (2500, 7500, 350, 350, 12, 2, 1400),
            (600, 800, 200, 200, 34, 40, 500),
            (600, 1600, 200, 200, 34, 40, 500),
            (2000, 2400, 200, 200, 34, 40, 500),
            (2800, 3200, 200, 200, 34, 40, 500),
            (3000, 4000, 200, 200, 34, 40, 500),
            (3200, 6400, 200, 200, 34, 40, 500),
            (3200, 8800, 200, 200, 34, 40, 500),
            (3200, 11200, 200, 200, 34, 40, 500),
            (3200, 14400, 200, 200, 34, 40, 500),
            (3200, 17600, 250, 250, 34, 40, 500),
            (3200, 19200, 250, 250, 34, 40, 500)
        ]
        for profile in profiles:
            self.assertEqual(assert_values[profile.idx], tuple(profile.dump()))

    def test_profile_overlay(self):
        profiles = MovingProfilesTowerSL1(
                factory_file_path=self.SAMPLES_DIR / "profiles_tower_overlay.json",
                default_file_path=self.DATA_DIR / "SL1" / "default_tower_moving_profiles.json")
        self.assertEqual(2499, profiles.homingFast.starting_steprate)
        self.assertEqual(7500, profiles.homingSlow.maximum_steprate)


if __name__ == '__main__':
    unittest.main()
