# This file is part of the SLA firmware
# Copyright (C) 2020 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import unittest
from tempfile import TemporaryDirectory
from time import sleep
from unittest.mock import patch

import pydbus

from slafw import defines
from slafw.api.examples0 import Examples0
from slafw.api.printer0 import Printer0
from slafw.states.examples import ExamplesState
from slafw.tests.integration.base import SlaFwIntegrationTestCaseBase
from slafw.tests.mocks.network import Network


class TestIntegrationExamples0(SlaFwIntegrationTestCaseBase):
    @patch("slafw.libPrinter.Network", Network)
    def setUp(self):
        super().setUp()
        self.printer0: Printer0 = pydbus.SystemBus().get("cz.prusa3d.sl1.printer0")

    def test_example_download(self):
        with TemporaryDirectory() as temp:
            defines.internalProjectPath = temp
            defines.internalProjectGroup = os.getegid()
            dbus_path = self.printer0.download_examples()
            self.assertEqual(
                dbus_path, "/cz/prusa3d/sl1/examples0", "Examples0 dbus path"
            )
            examples0 = pydbus.SystemBus().get(Examples0.__INTERFACE__)
            for _ in range(100):
                if ExamplesState(examples0.state) == ExamplesState.FAILURE:
                    break
                sleep(0.1)
            self.assertEqual(
                ExamplesState.COMPLETED,
                ExamplesState(examples0.state),
                "Fake network examples download",
            )


if __name__ == "__main__":
    unittest.main()
