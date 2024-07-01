# This file is part of the SLA firmware
# Copyright (C) 2020-2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import functools
import json
import logging
import tempfile
from threading import Thread
from time import sleep
from os import unlink

import pydbus

from slafw.admin.control import AdminControl
from slafw.admin.items import AdminAction, AdminTextValue
from slafw.admin.menu import AdminMenu
from slafw.admin.menus.dialogs import Error, Confirm
from slafw.functions.system import shut_down
from slafw.libPrinter import Printer


class NetUpdate(AdminMenu):
    FIRMWARE_LIST_URL = "https://sl1.prusa3d.com/check-update"

    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control)
        self._printer = printer
        self._status = "Downloading list of updates"

        self.add_back()
        self.add_label("<b>Custom updates to latest dev builds</b>", "network-icon")
        self.add_item(AdminTextValue.from_property(self, NetUpdate.status, "sandclock_color"))

        self._thread = Thread(target=self._download_list)
        self._thread.start()

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value: str):
        self._status = value

    def on_leave(self):
        self._thread.join()

    def _download_list(self):
        query_url = f"{self.FIRMWARE_LIST_URL}/?serial={self._printer.hw.cpuSerialNo}&version" \
                     f"={self._printer.hw.system_version}"

        with tempfile.TemporaryFile() as tf:
            self._printer.inet.download_url(
                query_url, tf, timeout_sec=5, progress_callback=self._download_callback
            )
            firmwares = json.load(tf)
            self.add_items(
                [
                    AdminAction(firmware["version"], functools.partial(self._install_fw, firmware), "firmware-icon")
                    for firmware in firmwares
                ]
            )
        self.del_item(self.items["status"])

    def _download_callback(self, progress: float):
        self.status = f"Downloading list of updates: {round(progress * 100)}%"

    def _install_fw(self, firmware):
        self._control.enter(
            Confirm(
                self._control,
                functools.partial(self._do_install_fw, firmware),
                headline=f"Really install firmware: {firmware['version']}?",
            )
        )

    def _do_install_fw(self, firmware):
        self._control.enter(FwInstall(self._control, self._printer, firmware))


class FwInstall(AdminMenu):
    def __init__(self, control: AdminControl, printer: Printer, firmware):
        super().__init__(control)
        self._logger = logging.getLogger(__name__)
        self._printer = printer
        self._firmware = firmware
        self._status = "Downloading firmware"

        self.add_label(f"<b>Updating firmware</b>\nVersion: {self._firmware['version']}", "sandclock_color")
        self.add_item(AdminTextValue.from_property(self, FwInstall.status, "sandclock_color"))

        self._thread = Thread(target=self._install, daemon=True)
        self._thread.start()

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value: str):
        self._status = value

    def _install(self):
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            self.fetch_update(self._firmware["url"], tf)
        self.do_update(tf.name)
        unlink(tf.name)

    def fetch_update(self, fw_url, file):
        try:
            self._printer.inet.download_url(fw_url, file, progress_callback=self._download_callback)
        except Exception as e:
            self._logger.error("Firmware fetch failed: %s", str(e))
            self._control.enter(Error(self._control, text="Firmware fetch failed"))

    def do_update(self, fw_file):
        self._logger.info("Flashing: %s", fw_file)
        try:
            rauc = pydbus.SystemBus().get("de.pengutronix.rauc", "/")["de.pengutronix.rauc.Installer"]
            rauc.InstallBundle(fw_file, {})
        except Exception as e:
            self._logger.error("Rauc install call failed: %s", str(e))
            self._control.enter(Error(self._control, text="Firmware install failed"))
            return

        self.status = "Updating firmware"

        try:
            while True:
                progress = rauc.Progress

                self.status = f"{progress[0]}<br/>{progress[1]}"

                # Check progress for update done
                if progress[1] == "Installing done.":
                    self.status = "Install done -> shutting down"
                    sleep(3)
                    shut_down(self._printer.hw, True)

                # Check for operation failure
                if progress[1] == "Installing failed.":
                    raise Exception(f"Update failed: {rauc.LastError}")
                # Wait for a while
                sleep(1)

        except Exception as e:
            self._logger.error("Rauc update failed: %s", str(e))
            self._control.enter(Error(self._control, text=str(e)))

    def _download_callback(self, progress: float):
        self.status = f"Downloading firmware: {round(progress * 100)}%"
