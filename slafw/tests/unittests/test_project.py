# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2024 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import unittest
from pathlib import Path

from slafw import defines
from slafw.configs.hw import HwConfig
from slafw.configs.unit import Ms, Nm, Ustep
from slafw.errors.errors import ProjectErrorNotFound, ProjectErrorNotEnoughLayers, \
                                ProjectErrorCorrupted, ProjectErrorWrongPrinterModel, \
                                ProjectErrorCantRead, ProjectErrorCalibrationInvalid
from slafw.errors.warnings import PrintingDirectlyFromMedia
from slafw.hardware.sl1.hardware import HardwareSL1
from slafw.project.project import Project, ProjectLayer, LayerCalibrationType
from slafw.tests.base import SlafwTestCase
from slafw.project.bounding_box import BBox
from slafw.hardware.printer_model import PrinterModel
from slafw.exposure.profiles import ExposureProfileSL1, EXPOSURE_PROFILES_DEFAULT_NAME


def _layer_generator(name, count, height_nm, times_ms, layer_times_ms):
    layers = []
    for i in range(count):
        layer = ProjectLayer(f'{name}{i:05d}.png', height_nm)
        if i >= len(layer_times_ms):
            times_ms[0] = layer_times_ms[-1]
        else:
            times_ms[0] = layer_times_ms[i]
        layer.times_ms = tuple(times_ms)
        if i < 10:
            layer.calibration_type = LayerCalibrationType.LABEL_PAD
        else:
            layer.calibration_type = LayerCalibrationType.LABEL_TEXT
        layers.append(layer)
    return layers


class TestProject(SlafwTestCase):
    def setUp(self):
        super().setUp()
        self.assertEqual.__self__.maxDiff = None
        self.hw_config = HwConfig(self.SAMPLES_DIR / "hardware.cfg")
        self.hw_config.read_file()
        self.hw = HardwareSL1(self.hw_config, PrinterModel.SL1)
        self.file2copy = self.SAMPLES_DIR / "Resin_calibration_object.sl1"
        (dummy, filename) = os.path.split(self.file2copy)
        self.destfile = defines.previousPrints / filename

    def test_notfound(self):
        with self.assertRaises(ProjectErrorNotFound):
            Project(self.hw, "bad_file")

    def test_empty(self):
        with self.assertRaises(ProjectErrorCantRead):
            Project(self.hw, str(self.SAMPLES_DIR / "empty_file.sl1"))

    def test_truncated(self):
        with self.assertRaises(ProjectErrorCantRead):
            Project(self.hw, str(self.SAMPLES_DIR / "test_truncated.sl1"))

    def test_nolayers(self):
        with self.assertRaises(ProjectErrorNotEnoughLayers):
            Project(self.hw, str(self.SAMPLES_DIR / "test_nolayer.sl1"))

    def test_corrupted(self):
        project = Project(self.hw, str(self.SAMPLES_DIR / "test_corrupted.sl1"))
        with self.assertRaises(ProjectErrorCorrupted):
            project.copy_and_check()

    def test_copy_and_check(self):
        project = Project(self.hw, str(self.file2copy))
        project.copy_and_check()
        self.assertFalse(PrintingDirectlyFromMedia() in project.warnings, "Printed directly warning issued")
        self.destfile.unlink()

    def test_avaiable_space_check_usb(self):
        statvfs = os.statvfs(defines.previousPrints.parent)
        backup = defines.internalReservedSpace
        defines.internalReservedSpace = statvfs.f_frsize * statvfs.f_bavail
        project = Project(self.hw, str(self.file2copy))
        project.copy_and_check()
        self.assertTrue(PrintingDirectlyFromMedia() in project.warnings, "Printed directly warning not issued")
        defines.internalReservedSpace = backup

    def test_avaiable_space_check_internal(self):
        statvfs = os.statvfs(defines.previousPrints.parent)
        backup1 = defines.internalReservedSpace
        backup2 = defines.internalProjectPath
        defines.internalReservedSpace = statvfs.f_frsize * statvfs.f_bavail
        defines.internalProjectPath = str(self.SAMPLES_DIR)
        project = Project(self.hw, str(self.file2copy))
        project.copy_and_check()
        self.assertFalse(PrintingDirectlyFromMedia() in project.warnings, "Printed directly warning issued")
        self.destfile.unlink()
        defines.internalReservedSpace = backup1
        defines.internalProjectPath = backup2

    def test_printer_model(self):
        hw = HardwareSL1(self.hw_config, PrinterModel.SL1S)
        with self.assertRaises(ProjectErrorWrongPrinterModel):
            Project(hw, str(self.SAMPLES_DIR / "numbers.sl1"))

    def test_read(self):
        project = Project(self.hw, str(self.SAMPLES_DIR / "numbers.sl1"))
        print(project)

        self.assertEqual(project.name, "numbers", "Check project name")
        self.assertEqual(project.total_layers, 2, "Check total layers count")
        self.assertEqual(project.total_height_nm, 1e5, "Total height calculation")
        self.assertAlmostEqual(project.modification_time, 1569863651.0, msg="Check modification time")

        result = _layer_generator('numbers', 2, 50000, [1000], (1000,))
        self.assertEqual(project.layers, result, "Base layers")
        #consumed_resin_slicer = project.used_material_nl / 1e6
        project.analyze()
        print(project)
        result[0].bbox = BBox((605, 735, 835, 1825))
        result[1].bbox = BBox((605, 735, 835, 1825))
        result[0].consumed_resin_nl = 26076
        result[1].consumed_resin_nl = 21153
        self.assertEqual(project.layers, result, "Analyzed base layers")
        # FIXME project usedMaterial is wrong (modified project)
        #self.assertAlmostEqual(consumed_resin_slicer, project.used_material_nl / 1e6, delta=0.1, msg="Resin count")

    def test_read_calibration(self):
        project = Project(self.hw, str(self.SAMPLES_DIR / "Resin_calibration_linear_object.sl1"))
        print(project)

        self.assertEqual(project.total_layers, 20, "Check total layers count")
        self.assertEqual(project.total_height_nm, 1e6, "Total height calculation")
        self.assertEqual(396434, project.count_remain_time(), "Total time calculation")
        self.assertEqual(project.count_remain_time(layers_done = 10), 182044, "Half time calculation")

        result = _layer_generator('sl1_linear_calibration_pattern',
                20,
                50000,
                [7500, 500, 500, 500, 500, 500, 500, 500, 500, 500],
                [35000, 21250, 7500])
        self.assertEqual(project.layers, result, "Calibration layers")
        consumed_resin_slicer = project.used_material_nl / 1e6
        project.analyze()
        print(project)
        project.analyze()
        self.assertAlmostEqual(consumed_resin_slicer, project.used_material_nl / 1e6, delta=0.1, msg="Resin count")
        # TODO analyze check

    def test_project_modification(self):
        project = Project(self.hw, str(self.SAMPLES_DIR / "Resin_calibration_linear_object.sl1"))
        with self.assertRaises(ProjectErrorCalibrationInvalid):
            project.calibrate_regions = 3

        # BIG TODO!
#        project.expTime = 5.0
#        self.assertAlmostEqual(project.expTime, 5.0, msg="Check expTime value")
#        self.assertEqual(project.calibrateAreas, [], "calibrateAreas")

        # project.config.write("projectconfig.txt")

    def test_project_with_json_config(self):
        self.hw = HardwareSL1(self.hw_config, PrinterModel.SL1S)
        project = Project(self.hw, str(self.SAMPLES_DIR / "numbers_json.sl1s"))
        profile = {
            "area_fill": 42,
            "below_area_fill": {
                "delay_before_exposure_ms": Ms(1),
                "delay_after_exposure_ms": Ms(2),
                "tower_hop_height_nm": Nm(1000000),
                "tower_profile": 14,  # layer22
                "use_tilt": True,
                "tilt_down_initial_profile": 11,  # layer1750
                "tilt_down_offset_steps": Ustep(3),
                "tilt_down_offset_delay_ms": Ms(4),
                "tilt_down_finish_profile": 15,  # layer8000
                "tilt_down_cycles": 2,
                "tilt_down_delay_ms": Ms(10),
                "tilt_up_initial_profile": 15,  # layer8000
                "tilt_up_offset_steps": Ustep(600),
                "tilt_up_offset_delay_ms": Ms(20),
                "tilt_up_finish_profile": 11,  # layer1750
                "tilt_up_cycles": 3,
                "tilt_up_delay_ms": Ms(30)
            },
            "above_area_fill": {
                "delay_before_exposure_ms": Ms(1000),
                "delay_after_exposure_ms": Ms(2000),
                "tower_hop_height_nm": Nm(500000),
                "tower_profile": 14,  # layer22
                "use_tilt": False,
                "tilt_down_initial_profile": 11,  # layer1750
                "tilt_down_offset_steps": Ustep(2),
                "tilt_down_offset_delay_ms": Ms(3),
                "tilt_down_finish_profile": 11,  # layer1750
                "tilt_down_cycles": 4,
                "tilt_down_delay_ms": Ms(5),
                "tilt_up_initial_profile": 15,  # layer8000
                "tilt_up_offset_steps": Ustep(601),
                "tilt_up_offset_delay_ms": Ms(6),
                "tilt_up_finish_profile": 11,  # layer1750
                "tilt_up_cycles": 5,
                "tilt_up_delay_ms": Ms(22)
            }
        }
        self.assertEqual(profile["area_fill"], project.exposure_profile.area_fill)
        for key, value in profile["above_area_fill"].items():
            self.assertEqual(value, getattr(project.exposure_profile.above_area_fill, key))
        for key, value in profile["below_area_fill"].items():
            self.assertEqual(value, getattr(project.exposure_profile.below_area_fill, key))

    def test_project_remaining_time_estimate(self):
        project = Project(self.hw, str(self.SAMPLES_DIR / "numbers.sl1"))
        # First numFade + 3 layer are forced to be slow. Therefore, this project
        # is printed with above_area_fill exposure profile.

        # 2 * 1000 ms - exposure_time
        # 2 * 1000 ms - fast.above_area_fill.delay_before_exposure_ms
        # 2 * 5674 ms - tilt time of fast.above_area_fill (SL1)
        # 2 * 124 ms - layers of tower move and magic computational delay constant
        # SUM: 15596 ms
        self.assertEqual(15596, project.count_remain_time(0, 0))

    def test_project_exposure_profile(self):
        project = Project(self.hw, str(self.SAMPLES_DIR / "layer_change.sl1"))
        file_name = "fast" + EXPOSURE_PROFILES_DEFAULT_NAME
        profile = ExposureProfileSL1(
            default_file_path=Path(defines.dataPath) / "SL1" / file_name)
        self.assertEqual(profile.as_dictionary(), project.exposure_profile.as_dictionary())

        project = Project(self.hw, str(self.SAMPLES_DIR / "layer_change_safe_profile.sl1"))
        file_name = "slow" + EXPOSURE_PROFILES_DEFAULT_NAME
        profile = ExposureProfileSL1(
            default_file_path=Path(defines.dataPath) / "SL1" / file_name)
        self.assertEqual(profile.as_dictionary(), project.exposure_profile.as_dictionary())

    def test_persistent_data(self):
        project = Project(self.hw, str(self.SAMPLES_DIR / "numbers.sl1"))
        persistent_data = project.persistent_data
        file_name = "fast" + EXPOSURE_PROFILES_DEFAULT_NAME
        profile = ExposureProfileSL1(
            default_file_path=Path(defines.dataPath) / "SL1" / file_name).as_dictionary()
        self.assertEqual({'path': str(self.SAMPLES_DIR / "numbers.sl1"),
                          'exposure_time_ms': 1000,
                          'exposure_time_first_ms': 1000,
                          'calibrate_time_ms': 1000,
                          'calibrate_regions': 0,
                          'exposure_profile': profile}, persistent_data)
        persistent_data['path'] = "XXX/YYY.ZZZ"
        persistent_data['exposure_time_ms'] = 999
        persistent_data['exposure_time_first_ms'] = 8888
        persistent_data['calibrate_time_ms'] = 777
        persistent_data['exposure_profile'] = profile
        persistent_data['exposure_profile']['area_fill'] = 42
        project.persistent_data = persistent_data
        self.assertEqual(persistent_data['path'], project.data.path)
        self.assertEqual(persistent_data['exposure_time_ms'], project.exposure_time_ms)
        self.assertEqual(persistent_data['exposure_time_first_ms'], project.exposure_time_first_ms)
        self.assertEqual(persistent_data['calibrate_time_ms'], project.calibrate_time_ms)
        self.assertEqual(persistent_data['exposure_profile']['area_fill'], project.exposure_profile.as_dictionary()["area_fill"])
        expected = _layer_generator('numbers', 2, 50000, [999], [8888, 8011])
        self.assertEqual(expected, project.layers)


if __name__ == '__main__':
    unittest.main()
