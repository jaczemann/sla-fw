# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2020 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from logging import Logger

from slafw import defines, test_runtime
from slafw.hardware.printer_model import PrinterModel
from slafw.hardware.hardware import BaseHardware


def get_save_path() -> Optional[Path]:
    """
    Dynamic USB path, first usb device or None

    :return: First usb device path or None
    """
    if test_runtime.testing:
        return Path(tempfile.tempdir)

    usbs = [p for p in Path(defines.mediaRootPath).glob("*") if p.is_mount()]
    if not usbs:
        return None
    return usbs[0]


def get_all_supported_files(printer_model: PrinterModel, path: Path) -> list:
    """
    Returns list of all supported files in specified path

    :param printer_model: PrinterModel enum
    :param path: which path to use

    :return: list of all supported files
    """
    files: List[Path] = []
    for extension in printer_model.extensions:  # type: ignore[attr-defined]
        files.extend(path.rglob(f"*{extension}"))
    return files


def save_wizard_history(filename: Path):
    # TODO: Limit history size
    timestamp = datetime.fromtimestamp(filename.stat().st_mtime).strftime("%Y-%m-%d_%H-%M-%S")
    if filename.parent == defines.factoryMountPoint:
        wizard_history = defines.wizardHistoryPath / f"{filename.stem}.{timestamp}{filename.suffix}"
    else:
        wizard_history = defines.wizardHistoryPathFactory / f"{filename.stem}.{timestamp}{filename.suffix}"
    wizard_history.parent.mkdir(parents=True, exist_ok=True)
    if not wizard_history.is_file():
        shutil.copyfile(filename, wizard_history)


def _save_wizard_history_bach(files: dict, source_path: Path):
    for name in files:
        filename = source_path / name
        if filename.is_file():
            save_wizard_history(filename)


def save_all_remain_wizard_history():
    _save_wizard_history_bach(
        ("hardware.toml", "uvcalib_data.toml", "wizard_data.toml"),
        defines.factoryMountPoint
    )

    _save_wizard_history_bach(
        ("uvcalib_data.toml", "wizard_data.toml", "hardware.cfg"),
        defines.configDir
    )


def ch_mode_owner(src):
    """
        change group and mode of the file or folder.
    """
    shutil.chown(src, group=defines.internalProjectGroup)
    if os.path.isdir(src):
        os.chmod(src, defines.internalProjectDirMode)
        for name in os.listdir(src):
            ch_mode_owner(os.path.join(src, name))
    else:
        os.chmod(src, defines.internalProjectMode)


def get_export_file_name(hw: BaseHardware) -> str:
    serial = re.sub("[^a-zA-Z0-9]", "_", hw.cpuSerialNo)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{serial}.{timestamp}"


def remove_files(logger: Logger, files: list) -> None:
    for file in files:
        logger.debug("removing '%s'", file)
        try:
            file.unlink()
        except FileNotFoundError:
            logger.debug("No such file '%s'", file)
        except Exception:
            logger.exception("remove_files() exception:")
