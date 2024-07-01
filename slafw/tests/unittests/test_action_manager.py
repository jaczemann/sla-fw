# This file is part of the SLA firmware
# Copyright (C) 2022-2024 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import unittest
from unittest.mock import Mock

from slafw.exposure.persistence import ExposurePickler
from slafw.image.exposure_image import ExposureImage
from slafw.state_actions.manager import ActionManager
from slafw.tests.base import SlafwTestCaseDBus, RefCheckTestCase
from slafw.tests.mocks.hardware import setupHw
from slafw.wizard.data_package import WizardDataPackage


class TestActionManager(SlafwTestCaseDBus, RefCheckTestCase):
    def setUp(self):
        super().setUp()
        self.hw = setupHw()
        exposure_image = Mock()
        exposure_image.__class__ = ExposureImage
        exposure_image.__reduce__ = lambda x: (Mock, ())
        exposure_image.sync_preloader.return_value = 100
        self.pickler = ExposurePickler(WizardDataPackage(self.hw, None, None, exposure_image))

    def tearDown(self):
        self.hw.exit()
        super().tearDown()

    def test_exposure_management(self):
        action_manager = ActionManager()
        exposure = action_manager.new_exposure(self.pickler, str(self.SAMPLES_DIR / "numbers.sl1"))
        exposure.project.exposure_time_first_ms = 20000
        self.pickler.save(exposure)
        action_manager.exit()

        action_manager = ActionManager()
        loaded_exposure = action_manager.load_exposure(self.pickler)
        new_exposure = action_manager.reprint_exposure(self.pickler, loaded_exposure)
        self.assertEqual(exposure.project.layers, new_exposure.project.layers)
        action_manager.exit()


if __name__ == "__main__":
    unittest.main()
