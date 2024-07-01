# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2020-2024 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
from logging.handlers import QueueHandler
from signal import signal, SIGTERM
from enum import unique, IntEnum, IntFlag
from multiprocessing import Process, shared_memory, Event, Queue
from queue import Empty
from time import monotonic
from typing import Optional, List, Any
import numpy
from PIL import Image

from slafw import defines
from slafw.hardware.exposure_screen import ExposureScreenParameters
from slafw.image.resin_calibration import Calibration
from slafw.image.cairo import inverse
from slafw.project.functions import get_white_pixels
from slafw.project.bounding_box import BBox


class ProjectFlags(IntFlag):
    NONE = 0
    CALIBRATE_COMPACT = 1
    USE_MASK = 2

@unique
class SHMIDX(IntEnum):
    PROJECT_IMAGE = 0
    PROJECT_MASK = 1
    OUTPUT_IMAGE = 2
    DISPLAY_USAGE = 3
    PROJECT_BBOX = 4
    PROJECT_FL_BBOX = 5
    PROJECT_TIMES_MS = 6

@unique
class SLIDX(IntEnum):
    PROJECT_SERIAL = 0
    PROJECT_FLAGS = 1
    PROJECT_CALIBRATE_REGIONS = 2
    PROJECT_CALIBRATE_PENETRATION_PX = 3
    PROJECT_CALIBRATE_TEXT_SIZE_PX = 4
    PROJECT_CALIBRATE_PAD_SPACING_PX = 5

class Preloader(Process):
    # pylint: disable=too-many-instance-attributes, too-many-arguments
    def __init__(self, exposure_screen_parameters: ExposureScreenParameters, start_preload: Queue, preload_result: Queue,
                 shm_prefix: str, log_queue: Queue):
        super().__init__()
        self._logger = logging.getLogger(__name__)
        self._log_queue = log_queue
        self._params = exposure_screen_parameters
        self._start_preload = start_preload
        self._preload_result = preload_result
        self._dev_shm_prefix = '/dev/shm/' + shm_prefix
        self._shm: Optional[List[Any]] = None  # TODO: List of heterogeneous types, "self._shm[SHMIDX.PROJECT_IMAGE].buf"
        self._sl: Optional[shared_memory.ShareableList] = None
        self._stoprequest = Event()
        self._display_usage_shape = (
                self._params.display_usage_size_px[0],
                self._params.thumbnail_factor,
                self._params.display_usage_size_px[1],
                self._params.thumbnail_factor,
        )
        self._black_image = Image.new("L", self._params.apparent_size_px)
        data = numpy.empty(shape=self._params.apparent_size_px, dtype=numpy.uint8)
        self._ppm1 = Image.frombytes("L", self._params.apparent_size_px, data)
        inverse(data, self._params.apparent_width_px, self._params.apparent_height_px)
        self._ppm2 = Image.frombytes("L", self._params.apparent_size_px, data)
        self._project_serial: Optional[int] = None
        self._calibration: Optional[Calibration] = None
        self._shm = [
                shared_memory.SharedMemory(name=shm_prefix+SHMIDX.PROJECT_IMAGE.name),
                shared_memory.SharedMemory(name=shm_prefix+SHMIDX.PROJECT_MASK.name),
                shared_memory.SharedMemory(name=shm_prefix+SHMIDX.OUTPUT_IMAGE.name),
                shared_memory.SharedMemory(name=shm_prefix+SHMIDX.DISPLAY_USAGE.name),
                shared_memory.ShareableList(name=shm_prefix+SHMIDX.PROJECT_BBOX.name),
                shared_memory.ShareableList(name=shm_prefix+SHMIDX.PROJECT_FL_BBOX.name),
                shared_memory.ShareableList(name=shm_prefix+SHMIDX.PROJECT_TIMES_MS.name)]
        self._sl = shared_memory.ShareableList(name=shm_prefix)

    def signal_handler(self, _signal, _frame):
        self._logger.debug("signal received")
        self._stoprequest.set()

    def join(self, timeout=None):
        self._stoprequest.set()
        return super().join(timeout)

    def run(self):
        queue_handler = QueueHandler(self._log_queue)
        logging.getLogger().handlers.clear()            # drop journald handler
        logging.getLogger().addHandler(queue_handler)   # log via main process logger
        self._logger.info("process started")
        self._logger.debug("process PID: %d", self.pid)
        signal(SIGTERM, self.signal_handler)

        while not self._stoprequest.is_set():
            try:
                calibration_type = self._start_preload.get(timeout=0.1)
            except Empty:
                continue
            except Exception:
                self._logger.exception("get calibration_type exception")
                continue
            try:
                self._preload_result.put(self._preload(calibration_type))
            except Exception:
                self._logger.exception("Preload failed")
                # TODO: We would need to recover from error or force resart of the printer.
                # This way all subsequent prints will end up with preloader timeout as this
                # kills the preloader process.
                raise

        if self._shm:
            for shm in self._shm:
                if shm and isinstance(shm, shared_memory.SharedMemory):
                    shm.close()
                else:
                    shm.shm.close()
        if self._sl:
            self._sl.shm.close()
        self._logger.info("process ended")

    @staticmethod
    def _read_SL(src) -> list:
        dst = []
        for i in range(src[0]):
            dst.append(src[i+1])
        return dst

    def _preload(self, calibration_type: int) -> int:
        start_time_first = monotonic()
        if self._project_serial != self._sl[SLIDX.PROJECT_SERIAL]:
            self._project_serial = self._sl[SLIDX.PROJECT_SERIAL]
            self._calibration = None
            if self._sl[SLIDX.PROJECT_CALIBRATE_REGIONS]:
                self._calibration = Calibration(self._params.apparent_size_px)
                if not self._calibration.new_project(
                        BBox(self._read_SL(self._shm[SHMIDX.PROJECT_BBOX])),
                        BBox(self._read_SL(self._shm[SHMIDX.PROJECT_FL_BBOX])),
                        self._sl[SLIDX.PROJECT_CALIBRATE_REGIONS],
                        self._sl[SLIDX.PROJECT_FLAGS] & ProjectFlags.CALIBRATE_COMPACT,
                        self._read_SL(self._shm[SHMIDX.PROJECT_TIMES_MS]),
                        self._sl[SLIDX.PROJECT_CALIBRATE_PENETRATION_PX],
                        self._sl[SLIDX.PROJECT_CALIBRATE_TEXT_SIZE_PX],
                        self._sl[SLIDX.PROJECT_CALIBRATE_PAD_SPACING_PX]):
                    self._logger.warning("Calibration is invalid!")
        input_image = Image.frombuffer("L", self._params.apparent_size_px, self._shm[SHMIDX.PROJECT_IMAGE].buf, "raw", "L", 0, 1)
        output_image = Image.frombuffer("L", self._params.apparent_size_px, self._shm[SHMIDX.OUTPUT_IMAGE].buf, "raw", "L", 0, 1)
        output_image.readonly = False
        if self._calibration and self._calibration.areas:
            start_time = monotonic()
            bbox = BBox(self._read_SL(self._shm[SHMIDX.PROJECT_BBOX]))
            crop = input_image.crop(bbox.coords)
            output_image.paste(self._black_image)
            for area in self._calibration.areas:
                area.paste(output_image, crop, calibration_type)
            self._logger.debug("multiplying done in %f ms", 1e3 * (monotonic() - start_time))
        else:
            output_image.paste(input_image)
        if self._sl[SLIDX.PROJECT_FLAGS] & ProjectFlags.USE_MASK:
            mask = Image.frombuffer("L", self._params.apparent_size_px, self._shm[SHMIDX.PROJECT_MASK].buf, "raw", "L", 0, 1)
            output_image.paste(self._black_image, mask=mask)
        start_time = monotonic()
        pixels = numpy.memmap(
                filename=self._dev_shm_prefix+SHMIDX.OUTPUT_IMAGE.name,
                dtype=numpy.uint8,
                mode='r',
                order='C')
        usage = numpy.memmap(
                filename=self._dev_shm_prefix+SHMIDX.DISPLAY_USAGE.name,
                dtype=numpy.float64,
                mode='r+',
                shape=self._params.display_usage_size_px,
                order='C')
        # 1500 layers on 0.1 mm layer height <0:255> -> <0.0:1.0>
        usage += numpy.reshape(pixels, self._display_usage_shape).mean(axis=3).mean(axis=1) / 382500
        white_pixels = get_white_pixels(output_image)
        self._logger.debug("pixels manipulations done in %f ms, white pixels: %d",
                1e3 * (monotonic() - start_time), white_pixels)
        self._screenshot(output_image)
        self._logger.debug("whole preload done in %f ms", 1e3 * (monotonic() - start_time_first))
        return white_pixels

    def _screenshot(self, image: Image):
        try:
            start_time = monotonic()
            preview = image.resize(self._params.live_preview_size_px, Image.BICUBIC)
            self._logger.debug("resize done in %f ms", 1e3 * (monotonic() - start_time))
            start_time = monotonic()
            preview.save(f"{defines.livePreviewImage}-tmp.png")
            self._logger.debug("screenshot done in %f ms", 1e3 * (monotonic() - start_time))
        except Exception:
            self._logger.exception("Screenshot exception:")
