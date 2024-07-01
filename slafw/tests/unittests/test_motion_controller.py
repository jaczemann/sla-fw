# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import os
from unittest.mock import patch, Mock

from slafw.errors.errors import MotionControllerWrongFw, MotionControllerException, MotionControllerWrongRevision
from slafw.motion_controller.sl1_controller import MotionControllerSL1
from slafw.tests.base import SlafwTestCase


class TestMotionController(SlafwTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.mcc = MotionControllerSL1()

    def tearDown(self) -> None:
        if os.path.isfile(self.EEPROM_FILE):
            os.remove(self.EEPROM_FILE)
        super().tearDown()

    def test_mcc_connect_ok(self) -> None:
        self.mcc.connect(mc_version_check=False)

    def test_mcc_connect_wrong_version(self) -> None:
        with patch("slafw.motion_controller.sl1_controller.MotionControllerSL1.REQUIRED_VERSION",
                   "INVALID"), self.assertRaises(
                MotionControllerWrongFw):
            self.mcc.connect(mc_version_check=True)

    def test_mcc_connect_fatal_fail(self) -> None:
        with patch("slafw.motion_controller.sl1_controller.MotionControllerSL1.getStateBits", Mock(return_value={
            'fatal': 1})):
            with self.assertRaises(MotionControllerException):
                self.mcc.connect(mc_version_check=False)

    def test_mcc_connect_rev_fail(self) -> None:
        with patch(
                "slafw.motion_controller.sl1_controller.MotionControllerSL1._get_board_revision", Mock(return_value=[5,
                                                                                                                   5])
        ):  # fw rev 5, board rev 5a
            with self.assertRaises(MotionControllerWrongRevision):
                self.mcc.connect(mc_version_check=False)

    def test_mcc_connect_board_rev_fail(self) -> None:
        with patch(
                "slafw.motion_controller.sl1_controller.MotionControllerSL1._get_board_revision", Mock(return_value=[5,
                                                                                                                  70])
        ):  # fw rev 5, board rev 6c
            with self.assertRaises(MotionControllerWrongFw):
                self.mcc.connect(mc_version_check=False)
