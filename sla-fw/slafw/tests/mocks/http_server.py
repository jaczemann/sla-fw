# This file is part of the SLA firmware
# Copyright (C) 2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later


from http.server import SimpleHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

from slafw.tests import samples


class MockHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, directory=Path(samples.__file__).parent)


class MockServer(HTTPServer, Thread):
    def __init__(self):
        HTTPServer.__init__(self, ("", 8000), MockHandler)
        Thread.__init__(self)

    def run(self):
        self.serve_forever()

    def stop(self):
        self.shutdown()
        self.join()
