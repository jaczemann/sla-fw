# This file is part of the SLA firmware
# Copyright (C) 2020 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio
import shutil
from asyncio.subprocess import Process
from pathlib import Path

from slafw import defines
from slafw.errors.errors import DisplayUsageError
from slafw.functions.generate import display_usage_heatmap
from slafw.functions.files import get_export_file_name
from slafw.hardware.hardware import BaseHardware
from slafw.state_actions.data_export import DataExport, UsbExport, ServerUpload
from slafw.state_actions.logs.summary import create_summary


def export_configs(temp_dir: Path):
    if defines.wizardHistoryPath.is_dir():
        shutil.copytree(defines.wizardHistoryPath, temp_dir / defines.wizardHistoryPath.name)
    if defines.wizardHistoryPathFactory.is_dir():
        shutil.copytree(defines.wizardHistoryPathFactory, temp_dir / defines.wizardHistoryPathFactory.name)
    if defines.configDir.exists():
        shutil.copytree(defines.configDir, temp_dir / defines.configDir.name)
    if defines.factoryMountPoint.exists():
        shutil.copytree(defines.factoryMountPoint, temp_dir / defines.factoryMountPoint.name)
        shutil.copyfile(defines.expoPanelLogPath, temp_dir / defines.expoPanelLogFileName)

async def run_log_export_process(data_file: Path) -> Process:
    return await asyncio.create_subprocess_shell(
        str(defines.script_dir / f"export_logs.sh '{data_file}'"),
        stderr=asyncio.subprocess.PIPE
    )

async def do_export(parent: DataExport, tmpdir_path: Path) -> Path:
    logs_dir = tmpdir_path / "logs"
    logs_dir.mkdir()
    log_file = logs_dir / "log.txt"
    summary_file = logs_dir / "summary.json"
    display_usage_file = logs_dir / "display_usage.png"

    parent.logger.info("Creating log export summary")
    summary = create_summary(parent.hw, parent.logger, summary_path = summary_file)
    if summary:
        parent.logger.debug("Log export summary created")
    else:
        parent.logger.error("Log export summary failed to create")

    parent.logger.info("Creating display usage heatmap")
    try:
        display_usage_heatmap(
                parent.hw.exposure_screen.parameters,
                defines.displayUsageData,
                defines.displayUsagePalette,
                display_usage_file)
    except DisplayUsageError as e:
        parent.logger.warning("Display usage heatmap not exported: %s", e.reason)
    except Exception:
        parent.logger.exception("Create display usage exception")

    parent.logger.debug("Running log export script")
    parent.proc = await run_log_export_process(log_file)

    parent.logger.debug("Waiting for log export to finish")
    _, stderr = await parent.proc.communicate()
    if parent.proc.returncode != 0:
        error = "Log export jounalctl failed to create"
        if stderr:
            error += f" - {stderr.decode()}"
        parent.logger.error(error)

    parent.logger.debug("Waiting for configs export to finish")
    try:
        export_configs(logs_dir)
    except Exception:
        parent.logger.exception("Config export exception")

    log_tar_file = tmpdir_path / f"logs.{get_export_file_name(parent.hw)}.tar.xz"
    if parent.file_name:
        log_tar_file = tmpdir_path / f"{parent.file_name}.tar.xz"
    parent.proc = await asyncio.create_subprocess_shell(
        f"tar -cf - -C '{tmpdir_path}' '{logs_dir.name}' | xz -T0 -0 > '{log_tar_file}'",
        stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await parent.proc.communicate()
    if parent.proc.returncode != 0:
        error = "Log compression failed"
        if stderr:
            error += f" - {stderr.decode()}"
        parent.logger.error(error)

    parent.proc = None

    if not log_tar_file.is_file():
        raise RuntimeError("Output file not exist")
    return log_tar_file


class UsbExportLogs(UsbExport):
    def __init__(self, hw: BaseHardware, file_name: str = None):
        super().__init__(hw, defines.last_log_token, do_export, file_name)


class ServerUploadLogs(ServerUpload):
    def __init__(self, hw: BaseHardware, url: str):
        super().__init__(hw, defines.last_log_token, do_export, url, "logfile")
