# This file is part of the SLA firmware
# Copyright (C) 2020 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import functools
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from slafw.tests.base import SlafwTestCaseDBus
from slafw.state_actions.examples import Examples
from slafw.states.examples import ExamplesState
from slafw.tests.mocks.network import fake_network_system_bus, Network
from slafw.hardware.printer_model import PrinterModel


class TestExamples(SlafwTestCaseDBus):
    def setUp(self) -> None:
        super().setUp()
        self.download_happening = False
        self.unpack_happening = False
        self.copy_happening = False

    def test_examples_fake_download(self):
        with TemporaryDirectory() as temp:
            chown = Mock()
            with patch("slafw.defines.internalProjectPath", temp), patch("os.chown", chown), patch(
                "shutil.chown", chown
            ), patch("pydbus.SystemBus", fake_network_system_bus):
                self._internal_examples_download()
            examples = list(Path(temp).rglob("*.sl1"))
            self.assertEqual(3, len(examples))
            chown.assert_called()
            self.assertTrue(self.download_happening, "Download progress reported")
            self.assertTrue(self.unpack_happening, "Unpacking progress reported")
            self.assertTrue(self.copy_happening, "Copy progress reported")

    def _internal_examples_download(self):
        network = Network()
        printer_model = PrinterModel.SL1
        examples = Examples(network, printer_model)
        examples.change.connect(functools.partial(self.check_change, examples))
        examples.start()
        examples.join(timeout=180)
        self.assertEqual(ExamplesState.COMPLETED, examples.state)

    def check_change(self, examples):
        self.assertTrue(0 <= examples.download_progress <= 100)
        self.assertTrue(0 <= examples.unpack_progress <= 100)
        self.assertTrue(0 <= examples.copy_progress <= 100)

        if 0 < examples.download_progress < 100:
            self.download_happening = True

        if 0 < examples.unpack_progress < 100:
            self.unpack_happening = True

        if 0 < examples.copy_progress < 100:
            self.copy_happening = True


if __name__ == "__main__":
    unittest.main()
