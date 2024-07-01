# This file is part of the SLA firmware
# Copyright (C) 2020-2024 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from functools import partial
import json
import re
import tempfile
from pathlib import Path
from threading import Thread
from time import sleep
from shutil import copy2, copyfile, make_archive, unpack_archive
from os import remove
from logging import Logger

from slafw import defines
from slafw.libPrinter import Printer
from slafw.admin.control import AdminControl
from slafw.admin.items import AdminAction, AdminLabel, AdminTextValue
from slafw.admin.menu import AdminMenu
from slafw.admin.safe_menu import SafeAdminMenu
from slafw.admin.menus.dialogs import Confirm, Error, Info, Wait
from slafw.functions.system import FactoryMountedRW, shut_down
from slafw.functions.files import get_export_file_name, get_save_path
from slafw.errors.errors import ConfigException
from slafw.state_actions.data_export import DataExport, UsbExport, ServerUpload
from slafw.states.data_export import ExportState
from slafw.hardware.hardware import BaseHardware
from slafw.hardware.sl1.tower_profiles import TOWER_CFG_LOCAL
from slafw.hardware.sl1.tilt_profiles import TILT_CFG_LOCAL


factory_configs = [
    defines.hwConfigPathFactory,
    defines.factory_enable,
    defines.serial_service_enabled,
    defines.ssh_service_enabled,
]
user_configs = [
    defines.hwConfigPath,
    defines.loggingConfig,
    TOWER_CFG_LOCAL,        # TODO based on printer model
    TILT_CFG_LOCAL,
]
filenamebase = "configs-"
factory_export_dir = "factory"
user_export_dir = "user"

config_api_url = "http://cucek.prusa/api/"

class BackupConfigMenu(AdminMenu):
    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control)
        self._printer = printer
        self.add_back()
        self.add_items(
            (
                AdminAction("Restore configuration from factory defaults", self.reset_to_defaults, "factory_color"),
                AdminAction("Save configuration as factory defaults", self.save_as_defaults, "save_color"),
                AdminAction(
                    "Restore configuration from USB drive",
                    lambda: self._control.enter(RestoreFromUsbMenu(self._control, self._printer)),
                    "usb_color"
                ),
                AdminAction("Save configuration to USB drive", self.save_to_usb, "usb_color"),
                AdminAction(
                    "Restore configuration from network",
                    lambda: self._control.enter(RestoreFromNetMenu(self._control, self._printer)),
                    "download"
                ),
                AdminAction("Save configuration to network", self.save_to_net, "upload_cloud_color"),
            ),
        )

    def reset_to_defaults(self):
        self._control.enter(
            Confirm(self._control, self._do_reset_to_defaults, text="Restore configuration from factory defaults?\n"
                                                                    "Printer will reboot after this operation.")
        )

    def _do_reset_to_defaults(self) -> None:
        self.logger.info("Restoring configuration to factory defaults")
        try:
            config = self._printer.hw.config
            config.read_file()
            config.factory_reset()
            config.showUnboxing = False
            config.vatRevision = self._printer.hw.printer_model.options.vat_revision    # type: ignore[attr-defined]
            self._printer.hw.uv_led.pwm = self._printer.hw.config.uvPwmPrint
            config.write()
        except ConfigException:
            self._control.enter(Error(self._control, text="Save configuration failed", pop=1))
            return
        shut_down(self._printer.hw, reboot=True)

    def save_as_defaults(self):
        self._control.enter(
            Confirm(self._control, self._do_save_as_defaults, text="Save configuration as factory defaults?")
        )

    def _do_save_as_defaults(self):
        self.logger.info("Saving configuration as factory defaults")
        try:
            self._printer.hw.config.write()
            with FactoryMountedRW():
                self._printer.hw.config.write_factory()
        except ConfigException:
            self._control.enter(Error(self._control, text="Save configuration as defaults failed", pop=1))
            return
        self._control.enter(Info(self._control, "Configuration saved as factory defaults"))

    def save_to_usb(self):
        self.enter(Wait(self._control, self._do_save_to_usb))

    @SafeAdminMenu.safe_call
    def _do_save_to_usb(self, status: AdminLabel):
        status.set("Saving to USB")
        exporter = UsbExportData(self._printer.hw)
        exporter.start()
        while exporter.state not in ExportState.finished_states():
            sleep(0.5)
        self._printer.hw.beepEcho()
        if exporter.state == ExportState.FINISHED:
            self._control.enter(Info(self._control, "Configs was saved successfully", pop=2))
        else:
            self._control.enter(Error(self._control,
                text=exporter.format_exception(),
                headline="Failed to save configs"))

    def save_to_net(self):
        self.enter(Wait(self._control, self._do_save_to_net))

    @SafeAdminMenu.safe_call
    def _do_save_to_net(self, status: AdminLabel):
        status.set("Saving to Cucek")
        exporter = ServerUploadData(self._printer.hw, config_api_url + "uploadConfig")
        exporter.start()
        while exporter.state not in ExportState.finished_states():
            sleep(0.5)
        self._printer.hw.beepEcho()
        if exporter.state == ExportState.FINISHED:
            self._control.enter(Info(self._control, "Configs was uploaded successfully", pop=2))
        else:
            self._control.enter(Error(self._control,
                text=exporter.format_exception(),
                headline="Failed to upload configs"))


async def do_export(parent: DataExport, tmpdir_path: Path) -> Path:
    tar_root = tmpdir_path / "tar_root"
    factory_path = tar_root / factory_export_dir
    factory_path.mkdir(parents=True, exist_ok=True)
    user_path = tar_root / user_export_dir
    user_path.mkdir(parents=True, exist_ok=True)
    for src in factory_configs:
        if src.is_file():
            copy2(src, factory_path, follow_symlinks=False)
        else:
            parent.logger.warning("Not exporting nonexistent file '%s'", src)
    for src in user_configs:
        if src.is_file():
            copy2(src, user_path, follow_symlinks=False)
        else:
            parent.logger.warning("Not exporting nonexistent file '%s'", src)
    tar_file = tmpdir_path / f"{filenamebase}{parent.hw.printer_model.name}.{get_export_file_name(parent.hw)}" # type: ignore[attr-defined]
    return Path(make_archive(tar_file, 'xztar', tar_root, logger=parent.logger))


def restore_config(logger: Logger, fullname: str):
    with tempfile.TemporaryDirectory() as tempdirname:
        unpack_archive(fullname, tempdirname, 'xztar')
        factory_path = Path(tempdirname) / factory_export_dir
        user_path = Path(tempdirname) / user_export_dir
        with FactoryMountedRW():
            for dst in factory_configs:
                src = factory_path / dst.name
                if src.is_file():
                    logger.info("Overwriting file '%s'", dst)
                    copyfile(src, dst, follow_symlinks=False)
                elif dst.is_file():
                    logger.info("Removing file '%s'", dst)
                    remove(dst)
        for dst in user_configs:
            src = user_path / dst.name
            if src.is_file():
                logger.info("Overwriting file '%s'", dst)
                copyfile(src, dst, follow_symlinks=False)
            elif dst.is_file():
                logger.info("Removing file '%s'", dst)
                remove(dst)


class UsbExportData(UsbExport):
    def __init__(self, hw: BaseHardware):
        super().__init__(hw, defines.last_log_token, do_export)


class ServerUploadData(ServerUpload):
    def __init__(self, hw: BaseHardware, url: str):
        super().__init__(hw, defines.last_log_token, do_export, url, "configfile")


class RestoreFromUsbMenu(SafeAdminMenu):
    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control)
        self._printer = printer
        self.add_back()
        usb_path = get_save_path()
        if usb_path is None:
            self.add_label("USB not present. To get files from USB, plug the USB\nand re-enter.", "error_small_white")
        else:
            name = printer.hw.printer_model.name  # type: ignore[attr-defined]
            if name in ["SL1S", "M1"]:
                filters = [filenamebase + "SL1S.*.tar.xz", filenamebase + "M1.*.tar.xz"]
            else:
                filters = [filenamebase + f"{name}.*.tar.xz",]
            self.list_files(usb_path, filters, self._confirm_restore, "usb_color")

    def _confirm_restore(self, path: Path, name: str):
        self._control.enter(Confirm(
            self._control,
            partial(self._restore_config, path, name),
            text=f"Restore from {name}?\n\nThe printer will restart."))

    @SafeAdminMenu.safe_call
    def _restore_config(self, path: Path, name: str):
        restore_config(self.logger, str(path / name))
        shut_down(self._printer.hw, reboot=True)


class RestoreFromNetMenu(SafeAdminMenu):
    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control)
        self._printer = printer
        self._status = "Downloading list of configs"
        self.add_back()
        self.add_item(AdminTextValue.from_property(self, RestoreFromNetMenu.status, "sandclock_color"))
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
        query_url = config_api_url + "listConfig"
        name = self._printer.hw.printer_model.name  # type: ignore[attr-defined]
        if name in ["SL1S", "M1"]:
            regex = re.compile(filenamebase + r"(SL1S|M1)\..*\.tar\.xz")
        else:
            regex = re.compile(filenamebase + fr"{name}\..*\.tar\.xz")
        with tempfile.TemporaryFile() as tf:
            self._printer.inet.download_url(
                query_url, tf, timeout_sec=5, progress_callback=self._download_callback
            )
            configs = json.load(tf)["results"]
            self.add_items(
                [
                     AdminAction(
                         config["tar"],
                         partial(self._confirm_restore, config["id"], config["tar"]),
                         "download")
                     for config in configs if regex.fullmatch(config["tar"])
                ]
            )
        self.del_item(self.items["status"])

    def _download_callback(self, progress: float):
        self.status = f"Downloading list of configs: {round(progress * 100)}%"

    def _confirm_restore(self, config_id: int, name: str):
        self._control.enter(Confirm(
            self._control,
            partial(self._restore_config, config_id),
            text=f"Restore from {name}?\n\nThe printer will restart."))

    @SafeAdminMenu.safe_call
    def _restore_config(self, config_id: int):
        query_url = config_api_url + f"fetchConfig?id={config_id}"
        with tempfile.NamedTemporaryFile() as tf:
            self._printer.inet.download_url(query_url, tf)
            restore_config(self.logger, tf.name)
        shut_down(self._printer.hw, reboot=True)
