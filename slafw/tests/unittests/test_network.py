# This file is part of the SLA firmware
# Copyright (C) 2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later


import unittest
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from tempfile import TemporaryFile
from unittest.mock import Mock

from slafw.libNetwork import Network
from slafw.tests import samples
from slafw.tests.base import SlafwTestCaseDBus, RefCheckTestCase
from slafw.tests.mocks.http_server import MockServer


class MockHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, directory=Path(samples.__file__).parent.name)


class TestExamples(SlafwTestCaseDBus, RefCheckTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.server = MockServer()
        self.server.start()

    def tearDown(self) -> None:
        self.server.stop()
        super().tearDown()

    def test_download(self):
        # pylint: disable = no-self-use
        network = Network("TEST", "1.0.0")
        with TemporaryFile() as temp:
            callback = Mock()
            network.download_url(
                "http://localhost:8000/mini_examples.tar.gz",
                temp,
                progress_callback=callback,
            )
            callback.assert_called()


if __name__ == "__main__":
    unittest.main()
