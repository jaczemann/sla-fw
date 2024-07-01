# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later


import logging
import tempfile
from io import BytesIO

from slafw import defines
from slafw.libNetwork import Network


class ProfileDownloader:

    INDEX_FILENAME = "index.idx"
    VERSION_SUFFIX = ".ini"

    def __init__(self, inet: Network, vendor: dict):
        self.logger = logging.getLogger(__name__)
        self.inet = inet
        self.vendor = vendor


    def check_updates(self) -> str:
        update_url = self.vendor.get('config_update_url', None)
        if not update_url:
            raise RuntimeError("Missing 'config_update_url' key")
        update_url += self.INDEX_FILENAME
        slicerMinVersion = None
        version, note = None, None
        with tempfile.TemporaryFile() as tf:
            self.inet.download_url(update_url, tf)
            while True:
                line = tf.readline().strip().decode('utf-8')
                if not line:
                    break
                if line.startswith("min_slic3r_version"):
                    slicerMinVersion = line.split("=")[1].strip()
                elif slicerMinVersion != defines.slicerMinVersion:
                    self.logger.debug("line '%s' is for different slicer version", line)
                else:
                    version, note = line.split(" ", 1)
                    self.logger.debug("Found version '%s' with note '%s'", version, note)
                    break
        if version != self.vendor.get('config_version', None):
            return version
        return ""


    def download(self, version: str, file: BytesIO) -> None:
        if not version:
            raise RuntimeError("Empty version")
        update_url = self.vendor.get('config_update_url', None)
        if not update_url:
            raise RuntimeError("Missing 'config_update_url' key")
        update_url += version + self.VERSION_SUFFIX
        self.inet.download_url(update_url, file)
