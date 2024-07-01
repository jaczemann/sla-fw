# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

# TODO: Fix following pylint problems
# pylint: disable=no-else-return

import json
import logging
import threading
import tempfile
from time import sleep
from abc import ABC, abstractmethod

from slafw import defines
from slafw.configs.runtime import RuntimeConfig
from slafw.hardware.hardware import BaseHardware
from slafw.libNetwork import Network
from slafw.slicer.profile_downloader import ProfileDownloader
from slafw.slicer.profile_parser import ProfileParser
from slafw.slicer.slicer_profile import SlicerProfile


class BackgroundNetworkCheck(ABC):
    def __init__(self, inet: Network):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.inet = inet
        self.change_trigger = True
        self.logger.info("Registering net change handler")
        self.inet.net_change.connect(self.connection_changed)

    def connection_changed(self, value):
        if value and self.change_trigger:
            self.logger.info("Starting background network check thread")
            threading.Thread(target=self._check, daemon=True).start()

    def _check(self):
        while True:
            run_after = self.check()
            if run_after is None:
                self.logger.warning("Check returned error, waiting for next connection change.")
                break
            self.change_trigger = False
            if not run_after:
                self.logger.debug("Check returned no repeat, exiting thread.")
                break
            self.logger.debug("Check returned repeat after %d secs, sleeping.", run_after)
            sleep(run_after)

    @abstractmethod
    def check(self):
        ...


class AdminCheck(BackgroundNetworkCheck):
    ADMIN_CHECK_URL = "https://sl1.prusa3d.com/check-admin"

    def __init__(self, config: RuntimeConfig, hw: BaseHardware, inet: Network):
        super().__init__(inet)
        self.config = config
        self.hw = hw
        self.logger.info("Starting admin checker")

    def check(self):
        self.logger.info("Querying admin enabled")
        query_url = self.ADMIN_CHECK_URL + "/?serial=" + self.hw.cpuSerialNo
        with tempfile.TemporaryFile() as tf:
            try:
                self.inet.download_url(query_url, tf)
            except Exception:
                self.logger.exception("download_url exception:")
                return None
            admin_check = json.load(tf)
            result = admin_check.get("result", None)
            if result is None:
                self.logger.warning("Error querying admin enabled")
                return None
            elif result:
                self.config.show_admin = True
                self.logger.info("Admin enabled")
            else:
                self.logger.info("Admin not enabled")
        return 0


class SlicerProfileUpdater(BackgroundNetworkCheck):
    def __init__(self, inet: Network, profile: SlicerProfile, printer_type_name: str):
        self.profile = profile
        self.printer_type_name = printer_type_name
        super().__init__(inet)

    def check(self):
        self.logger.info("Checking slicer profiles update")
        downloader = ProfileDownloader(self.inet, self.profile.vendor)
        try:
            new_version = downloader.check_updates()
            if new_version:
                with tempfile.NamedTemporaryFile() as tf:
                    downloader.download(new_version, tf)
                    new_profile = ProfileParser(self.printer_type_name).parse(tf.name)
                    if new_profile and new_profile.save(filename = defines.slicerProfilesFile):
                        self.profile.data = new_profile.data
                        return defines.slicerProfilesCheckOK
                    else:
                        self.logger.warning("Problem with new profile file, giving up")
            else:
                self.logger.info("No new version of slicer profiles available")
                return defines.slicerProfilesCheckOK
        except Exception:
            self.logger.exception("Exception, giving up")

        return defines.slicerProfilesCheckProblem
