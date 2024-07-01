# This file is part of the SLA firmware
# Copyright (C) 2020 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio
import errno
import json
import logging
import re
import shutil
import tempfile
from abc import ABC, abstractmethod
from asyncio import CancelledError
from asyncio.subprocess import Process
from io import BufferedReader
from pathlib import Path
from threading import Thread
from typing import Optional, Callable

import aiohttp
from PySignal import Signal
from aiohttp.client_exceptions import ClientConnectorError

from slafw.errors.errors import NotConnected, ConnectionFailed, NotEnoughInternalSpace, NoExternalStorage
from slafw.functions.files import get_save_path
from slafw.hardware.hardware import BaseHardware
from slafw.states.data_export import ExportState, StoreType


class DataExport(ABC, Thread):
    # pylint: disable=too-many-instance-attributes
    def __init__(self, hw: BaseHardware, last_token_path: Path, do_export, file_name: Optional[str] = None):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self._state = ExportState.IDLE
        self.state_changed = Signal()
        self._export_progress: float = 0
        self.export_progress_changed = Signal()
        self._store_progress: float = 0
        self.store_progress_changed = Signal()
        self._task: Optional[asyncio.Task] = None
        self._exception: Optional[Exception] = None
        self.exception_changed = Signal()
        self.hw = hw
        self.last_token_path = last_token_path
        self.do_export = do_export
        self._uploaded_data_identifier: Optional[str] = None
        self.uploaded_data_identifier_changed = Signal()
        self._uploaded_data_url: Optional[str] = None
        self.uploaded_data_url_changed = Signal()
        self.proc: Optional[Process] = None
        self.file_name = file_name

    @property
    def state(self) -> ExportState:
        return self._state

    @state.setter
    def state(self, value: ExportState):
        if self._state != value:
            self._state = value
            self.state_changed.emit(value)

    @property
    @abstractmethod
    def type(self) -> StoreType:
        ...

    @property
    def export_progress(self) -> float:
        return self._export_progress

    @export_progress.setter
    def export_progress(self, value: float) -> None:
        if self._export_progress != value:
            self._export_progress = value
            self.export_progress_changed.emit(value)

    @property
    def store_progress(self) -> float:
        return self._store_progress

    @store_progress.setter
    def store_progress(self, value: float) -> None:
        if self._store_progress != value:
            self._store_progress = value
            self.store_progress_changed.emit(value)

    @property
    def data_upload_identifier(self) -> str:
        return self._uploaded_data_identifier

    @data_upload_identifier.setter
    def data_upload_identifier(self, value: str) -> None:
        if self._uploaded_data_identifier != value:
            self._uploaded_data_identifier = value
            self.uploaded_data_identifier_changed.emit(value)
            with self.last_token_path.open("w") as f:
                f.write(str(value))

    @property
    def last_data_upload_identifier(self) -> str:
        try:
            with self.last_token_path.open("r") as f:
                return f.read()
        except FileNotFoundError:
            return ""

    @property
    def data_upload_url(self) -> str:
        return self._uploaded_data_url

    @data_upload_url.setter
    def data_upload_url(self, value: str) -> None:
        if self._uploaded_data_url != value:
            self._uploaded_data_url = value
            self.uploaded_data_url_changed.emit(value)

    @property
    def exception(self) -> Optional[Exception]:
        return self._exception

    @exception.setter
    def exception(self, value: Exception):
        if self.exception != value:
            self._exception = value
            self.exception_changed.emit(value)

    def format_exception(self) -> str:
        if self._exception:
            return f"{type(self._exception).__name__}\n{Exception.__str__(self._exception)}"
        return ""

    def cancel(self) -> None:
        if not self._task:
            self.logger.warning("Attempt to cancel data export, but no export in progress")
            return

        try:
            if self.proc:
                self.proc.kill()
        except ProcessLookupError:
            pass

        self._task.cancel()

    def run(self):
        self.logger.info("Running data export of type %s", self.type)
        asyncio.run(self.async_run())

    async def async_run(self):
        try:
            self._task = asyncio.create_task(self.run_export())
            await self._task
            self.state = ExportState.FINISHED
        except CancelledError:
            self.state = ExportState.CANCELED
        except Exception as exception:
            self.exception = exception
            self.state = ExportState.FAILED

    async def run_export(self):
        self.state = ExportState.EXPORTING
        with tempfile.TemporaryDirectory() as tmpdirname:
            tmpdir_path = Path(tmpdirname)

            self.logger.debug("Exporting data data to a temporary file")
            self.export_progress = 0
            try:
                data_tar_file = await self.do_export(self, tmpdir_path)
                self.export_progress = 1
            except shutil.Error as exception:
                # shutil.Error concatenates the OSError errors like [(src, dst, str(why),]
                if exception.args:
                    code_re = re.compile(r"\[Errno\s*([0-9]*)\]")
                    args = exception.args[0]
                    for e in args:
                        why = e[-1]
                        error_no = int(code_re.search(why).group(1))
                        if error_no == errno.ENOSPC:
                            self.logger.error(why)
                            raise NotEnoughInternalSpace(why) from exception
                raise
            except OSError as exception:
                if exception.errno == errno.ENOSPC:
                    self.logger.error(exception.strerror)
                    raise NotEnoughInternalSpace(exception.strerror) from exception
                raise

            self.logger.debug("Running store data method")
            self.state = ExportState.SAVING
            self.store_progress = 0
            await self.store_data(data_tar_file)
            self.store_progress = 1

    @abstractmethod
    async def store_data(self, src: Path):
        ...


class UsbExport(DataExport):
    async def store_data(self, src: Path):
        self.state = ExportState.SAVING
        save_path = get_save_path()
        if save_path is None or not save_path.parent.exists():
            raise NoExternalStorage()

        self.logger.debug("Copying temporary data file to usb")
        await self._copy_with_progress(src, save_path / src.name)

    async def _copy_with_progress(self, src: Path, dst: Path):
        with src.open("rb") as src_file, dst.open("wb") as dst_file:
            block_size = 4096
            total_size = src.stat().st_size
            while True:
                data = src_file.read(block_size)
                if not data:
                    break
                dst_file.write(data)
                self.store_progress = dst_file.tell() / total_size
                await asyncio.sleep(0)

    @property
    def type(self) -> StoreType:
        return StoreType.USB


class FileReader(BufferedReader):
    """
    This mimics file object and wraps read access while providing callback for current file position

    CHUNK_SIZE constant is used for file upload granularity control
    """

    CHUNK_SIZE = 8192

    def __init__(self, file, callback: Callable[[int, int], None] = None):
        self._total_size = Path(file.name).stat().st_size
        super().__init__(file, self._total_size)
        self._file = file
        self._callback = callback

    def read(self, size=-1):
        data = self._file.read(min(self.CHUNK_SIZE, size))
        if self._callback:
            self._callback(self._file.tell(), self._total_size)
        return data


class ServerUpload(DataExport):
    DATA_UPLOAD_TOKEN = "84U83mUQ"

    # pylint: disable=too-many-arguments
    def __init__(self, hw: BaseHardware, last_token_path: Path, do_export, url: str, file_keyword: str):
        super().__init__(hw, last_token_path, do_export)
        self._url = url
        self._file_keyword = file_keyword

    async def store_data(self, src: Path):

        self.logger.info("Uploading temporary data file to the server")

        async with aiohttp.ClientSession(headers={"user-agent": "OriginalPrusa3DPrinter"}) as session:
            self.logger.debug("Opening aiohttp client session")

            with src.open("rb") as file:
                data = aiohttp.FormData()
                data.add_field(
                    self._file_keyword,
                    FileReader(file, callback=self._callback),
                    filename=src.name,
                    content_type="application/x-xz",
                )
                data.add_field("token", self.DATA_UPLOAD_TOKEN)
                data.add_field("serial", self.hw.cpuSerialNo)

                try:
                    async with session.post(url=self._url, data=data) as response:
                        if response.status == 200:
                            self.logger.debug("aiohttp post done")
                            response_text = await response.text()
                            self.logger.debug("Data upload response: %s", response_text)
                            response_data = json.loads(response_text)
                            self.data_upload_identifier = response_data["id"] if "id" in response_data else response_data["url"]
                            self.data_upload_url = response_data["url"]
                        else:
                            strerror = f"Cannot connect to host {self._url} [status code: {response.status}]"
                            self.logger.error(strerror)
                            raise ConnectionFailed(strerror)
                except ClientConnectorError as exception:
                    self.logger.error(exception.strerror)
                    raise NotConnected(exception.strerror) from exception

    @property
    def type(self) -> StoreType:
        return StoreType.UPLOAD

    def _callback(self, position: int, total_size: int):
        self.logger.debug("Current upload position: %s / %s bytes", position, total_size)
        self.store_progress = position / total_size
