# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

# TODO: Fix following pylint problems
# pylint: disable=too-many-instance-attributes

import logging
import os
from time import monotonic
from typing import Optional, Any, Dict, Callable
from urllib.request import urlopen, Request
from io import BytesIO

import pydbus
from PySignal import Signal

from slafw import test_runtime
from slafw.errors.errors import DownloadFailed


class Network:
    NETWORKMANAGER_SERVICE = "org.freedesktop.NetworkManager"
    NM_STATE_CONNECTED_GLOBAL = 70
    REPORT_INTERVAL_S = 0.25
    NM_DEVICE_TYPE_ETHERNET = 1

    def __init__(self, cpu_serial_no: str, system_version: str):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing")
        self.version_id = system_version
        self.cpu_serial_no = cpu_serial_no
        self.assign_active = None
        self.net_change = Signal()
        self._bus = pydbus.SystemBus()
        self._nm = self._bus.get(self.NETWORKMANAGER_SERVICE)

    def register_events(self) -> None:
        """
        Start network monitoring
        Use net_change signal to register for network state updates

        :return: None
        """
        self._nm.StateChanged.connect(self._state_changed)
        for device_path in self._nm.GetAllDevices():
            device = self._bus.get(self.NETWORKMANAGER_SERVICE, device_path)
            device.StateChanged.connect(self._device_state_changed)

    def force_refresh_state(self):
        self.net_change.emit(self.online)

    @property
    def online(self) -> bool:
        return self._nm.state() == self.NM_STATE_CONNECTED_GLOBAL

    def _state_changed(self, state) -> None:
        self.force_refresh_state()
        self.logger.debug("NetworkManager state changed: %s", state)

    def _device_state_changed(self, new_state, old_state, reason):
        self.force_refresh_state()
        self.logger.debug("NetworkManager device changed: %s -> %s (%s)", old_state, new_state, reason)

    @property
    def ip(self) -> Optional[str]:
        connection_path = self._nm.PrimaryConnection

        if connection_path == "/":
            return None

        return self._get_ipv4(self._get_nm_obj(connection_path).Ip4Config)

    @property
    def devices(self) -> Dict[str, str]:
        """
        Get network device dictionary

        :return: {interface_name: ip_address}
        """
        if test_runtime.testing:
            return {}

        return {
            dev.Interface: self._get_ipv4(dev.Ip4Config)
            for dev in [self._get_nm_obj(dev_path) for dev_path in self._nm.GetAllDevices()]
            if dev.Interface != "lo" and dev.Ip4Config != "/"
        }

    def _get_ipv4(self, ipv4_config_path: str) -> Optional[str]:
        """
        Resolves IPv4 address string from NetworkManager ipv4 configuration object path

        :param ipv4_config_path: D-Bus path to NetworkManager ipv4 configuration
        :return: IP address as string or None
        """
        if ipv4_config_path == "/":
            return None

        ipv4 = self._get_nm_obj(ipv4_config_path)

        if not ipv4.AddressData:
            return None

        return ipv4.AddressData[0]["address"]

    def _get_nm_obj(self, path: str) -> Any:
        """
        Get NetworkManager D-Bus object by path
        :param path:
        :return:
        """
        return self._bus.get(self.NETWORKMANAGER_SERVICE, path)

    # TODO: Fix Pylint warnings
    # pylint: disable = too-many-branches
    def download_url(
        self,
        url: str,
        file: BytesIO,
        timeout_sec=10,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> None:
        """
        Fetches data specified by url info file while displaying progress

        This is implemented as chunked copy from source file descriptor to the destination file descriptor. The progress
        is updated once the chunk is copied. The source file descriptor is either standard file when the source is
        mounted USB drive or urlopen result.

        :param url: Source url
        :param file: Destination file descriptor
        :param timeout_sec: Timeout in seconds
        :param progress_callback: Progress reporting function
        :return: None
        """
        if progress_callback:
            progress_callback(0)

        self.logger.info("Downloading %s", url)

        if url.startswith("http://") or url.startswith("https://"):
            # URL is HTTP, source is url
            req = Request(url)
            req.add_header("User-Agent", "Prusa-SLA")
            req.add_header("Prusa-SLA-version", self.version_id)
            req.add_header("Prusa-SLA-serial", self.cpu_serial_no)
            source = urlopen(req, timeout=timeout_sec)

            # Default files size (sometimes HTTP server does not know size)
            content_length = source.info().get("Content-Length")
            if content_length is not None:
                file_size = int(content_length)
            else:
                file_size = None

            block_size = 8 * 1024
        else:
            # TODO do we still need this functionality?
            # URL is file, source is file
            self.logger.info("Copying file %s", url)
            source = open(url, "rb")  # pylint: disable = consider-using-with
            file_size = os.path.getsize(url)
            block_size = 1024 * 1024

        try:
            last_report_s = monotonic()
            while True:
                buffer = source.read(block_size)
                if not buffer or buffer == "":
                    break
                file.write(buffer)

                if file_size is not None:
                    progress = file.tell() / file_size
                else:
                    progress = 0

                if monotonic() - last_report_s > self.REPORT_INTERVAL_S or progress == 1:
                    last_report_s = monotonic()
                    if progress_callback:
                        progress_callback(progress)

            if file_size and file.tell() != file_size:
                raise DownloadFailed(url, file_size, file.tell())
            file.seek(0)
        finally:
            source.close()

    def get_eth_mac(self):
        for device_path in self._nm.Devices:
            dev = pydbus.SystemBus().get(self.NETWORKMANAGER_SERVICE, device_path)
            if dev.DeviceType == self.NM_DEVICE_TYPE_ETHERNET:
                return dev.HwAddress.replace(":", "")
        return None
