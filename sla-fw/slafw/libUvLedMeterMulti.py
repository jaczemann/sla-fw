# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

# TODO: Fix following pylint problems
# pylint: disable=inconsistent-return-statements
# pylint: disable=no-else-return
# pylint: disable=too-many-instance-attributes
# pylint: disable=too-many-arguments
# pylint: disable=too-many-locals
# pylint: disable=too-many-statements


import logging
import os
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum, unique
from time import sleep
from typing import Optional

import numpy
import serial
import serial.tools.list_ports
from PIL import Image, ImageDraw, ImageFont

from slafw import defines, test_runtime


@dataclass(init=False)
class UvCalibrationData:
    # following values are measured and saved in automatic UV LED calibration
    uvSensorType: int  # 0=multi
    uvSensorData: list
    uvTemperature: float
    uvDateTime: str
    uvMean: float
    uvStdDev: float
    uvMinValue: int
    uvMaxValue: int
    uvPercDiff: list
    uvFoundPwm: int


@dataclass()
class UVCalibrationResult:
    data: Optional[UvCalibrationData] = None
    boost: bool = False


@unique
class UvMeterState(IntEnum):
    OK = 0
    ERROR_COMMUNICATION = 1
    ERROR_TRANSLUCENT = 2
    ERROR_INTENSITY = 3


class UvLedMeterMulti:

    uvLedMeterDevice = defines.uv_meter_device
    uvSensorType = 0

    WEIGHTS60 = numpy.array(
        [0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30]
        + [0.30, 0.75, 0.75, 0.75, 0.75, 0.75, 0.75, 0.75, 0.75, 0.30]
        + [0.30, 0.75, 1.30, 1.30, 1.30, 1.30, 1.30, 1.30, 0.75, 0.30]
        + [0.30, 0.75, 1.30, 1.30, 1.30, 1.30, 1.30, 1.30, 0.75, 0.30]
        + [0.30, 0.75, 0.75, 0.75, 0.75, 0.75, 0.75, 0.75, 0.75, 0.30]
        + [0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30]
    )
    WEIGHTS15 = numpy.array([0.50, 0.50, 0.50, 0.50, 0.50, 0.50, 1.30, 1.00, 1.30, 0.50, 0.50, 0.50, 0.50, 0.50, 0.50])

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.ndigits = 1
        self.port = None
        self.np = None
        self.temp = None
        self.datetime = None
        self.sleepTime = 3
        self.sixty_points = False

    @property
    def present(self):
        return os.path.exists(self.uvLedMeterDevice) or test_runtime.testing and test_runtime.test_uvmeter_present

    def connect(self):
        try:
            self._low_level_connect()
        except Exception:
            self.logger.exception("UV calibrator connect failed with exception")
            return False
        return True

    def _low_level_connect(self, retries: int = 3):
        self.logger.info("Connecting to the UV calibrator, retries: %d", retries)
        try:
            self.port = serial.Serial(
                port=self.uvLedMeterDevice,
                baudrate=115200,
                bytesize=8,
                parity="N",
                stopbits=1,
                timeout=1.0,
                writeTimeout=1.0,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
                interCharTimeout=None,
            )

            self.logger.info("Waiting for UV calibrator response")
            timeout = 100
            while not self.port.inWaiting() and timeout:
                sleep(0.1)
                timeout -= 1

            if not timeout:
                self.logger.error("Response timeout")
                raise TimeoutError("Response timeout")

            reply = None
            while reply != "<done":
                reply = self.port.readline().strip().decode()
                self.logger.debug("UV calibrator response: %s", reply)

            if not test_runtime.testing:
                devices = serial.tools.list_ports.comports()
                if len(devices) > 1:
                    self.logger.warning("Multiple devices attached: %d", len(devices))
                if devices[0].vid == 0x10C4 and devices[0].pid == 0xEA60:  # 60p UV calibrator
                    self.logger.info("60p UV calibrator is present")
                    self.sleepTime = 3
                    self.sixty_points = True
                elif devices[0].vid == 0x1A86 and devices[0].pid == 0x7523:  # 15p UV calibrator
                    self.logger.info("15p UV calibrator is present")
                    self.sleepTime = 0.5
                    self.sixty_points = False
                else:
                    self.logger.warning("Unknown device connected. VID: %x, PID: %x", devices[0].vid, devices[0].pid)
            else:
                self.logger.warning("Skipping UV calibrator device detection due to testing")

            self.logger.info("UV calibrator connected successfully")

        except Exception as e:
            self.logger.exception("Connection failed:")
            if retries > 0:
                self.logger.warning("Reconnecting, retries: %s", retries)
                self.logger.debug("Waining 1 sec to reconnect")
                sleep(1)
                self.logger.debug("Reconnecting UV calibrator now")
                return self._low_level_connect(retries - 1)
            raise e

    def close(self):
        if self.port is not None:
            self.port.close()

        self.port = None

    def read(self):
        self.logger.info("Reading UV calibrator data")
        if not test_runtime.testing:
            sleep(self.sleepTime)
        self.np = None
        try:
            line = self._low_level_read(retries = 3)

            if line[0] != "<":
                self.logger.error("Invalid response - wrong line format")
                return False

            data = list([float(x) for x in line[1:].split(",")])
        except Exception:
            self.logger.exception("Invalid response:")
            return False

        if len(data) not in (16, 61):
            self.logger.error("Invalid response - wrong line items")
            return False

        self.temp = data[-1] / 10.0
        self.np = numpy.array(data[:-1])
        self.datetime = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        return True

    def _low_level_read(self, retries: int) -> str:
        try:
            self.port.write(">all\n".encode())
            self.logger.debug("UV calibrator command reply: %s", self.port.readline().strip().decode())
            timeout = defines.uvLedMeterMaxWait_s * 10
            while not self.port.inWaiting() and timeout:
                sleep(0.1)
                timeout -= 1

            if not timeout:
                raise TimeoutError("UV calibrator response timeout")

            line = self.port.readline().strip().decode()
            self.logger.debug("UV calibrator response: %s", line)
            return line
        except (TimeoutError, IOError) as e:
            self.logger.error("Error reading UV calibrator")
            if retries > 0:
                self.logger.warning("Reconnecting, Retrying UV calibrator read: %s", retries)
                self.connect()
                return self._low_level_read(retries - 1)
            else:
                self.logger.error("Too many UV calibrator read retries")
                raise e

    def get_data(self, plain_mean=False):
        data = UvCalibrationData()
        data.uvSensorType = self.uvSensorType
        if self.np is None:
            data.uvSensorData = None
            data.uvTemperature = None
            data.uvDateTime = None
            data.uvMean = None
            data.uvStdDev = None
            data.uvMinValue = None
            data.uvMaxValue = None
            data.uvPercDiff = None
        else:
            # float and int type conversions from numpy data types are required for toml save algorithm
            if plain_mean:
                mean = numpy.average(self.np)
            else:
                mean = numpy.average(self.np, weights=self.WEIGHTS60 if len(self.np) == 60 else self.WEIGHTS15)
            data.uvSensorData = self.np.tolist()
            data.uvTemperature = round(self.temp, self.ndigits)
            data.uvDateTime = self.datetime
            data.uvMean = float(round(mean, self.ndigits))
            data.uvStdDev = float(round(self.np.std(), self.ndigits))
            data.uvMinValue = int(self.np.min())
            data.uvMaxValue = int(self.np.max())
            data.uvPercDiff = ((self.np - mean) / (mean / 100.0)).round(self.ndigits).tolist() if mean > 0 else []

        return data

    def read_data(self):
        if self.read():
            return self.get_data()
        else:
            return None

    def check_place(self, screenOn):
        self.logger.info("Checking UV calibrator placement")
        self.read()
        if self.np is None:
            return UvMeterState.ERROR_COMMUNICATION

        data = self.get_data()
        if data.uvMean > 1.0 or data.uvMaxValue > 2:
            return UvMeterState.ERROR_TRANSLUCENT

        screenOn()
        sleep(1)  # wait just to be sure display really opens
        self.read()
        if self.np is None:
            return UvMeterState.ERROR_COMMUNICATION

        if self.np.min() < 3:
            return UvMeterState.ERROR_INTENSITY

    def save_pic(self, width, height, text, filename, data):
        bg_color = (0, 0, 0)
        text_color = (255, 255, 255)
        perc_plus_color = (0, 255, 0)
        perc_minus_color = (255, 0, 0)
        font_size = height // 16
        font_small_size = height // 30

        values = data.get("uvSensorData", None)
        if values is None:
            self.logger.warning("No data to show")
            return False

        if len(values) == 60:
            cols = 10
            rows = 6
        else:
            cols = 5
            rows = 3

        perc = data["uvPercDiff"]
        if not perc:
            perc = len(values) * list((0,))

        image = Image.new("RGB", (width, height))
        font = ImageFont.truetype(defines.fontFile, font_size)
        metrics = font.getmetrics()
        text_size = metrics[0] + metrics[1]
        font_small = ImageFont.truetype(defines.fontFile, font_small_size)
        step_x = int(width / cols)
        step_y = int((height - text_size) / rows)
        val_diff = data["uvMaxValue"] - data["uvMinValue"]
        if val_diff:
            step_color = 192.0 / val_diff
        else:
            step_color = 0

        surf = ImageDraw.Draw(image)

        surf.rectangle(((0, 0), (width, text_size)), bg_color)
        state = f"ø {data['uvMean']:.1f}  σ {data['uvStdDev']:.1f}  {data['uvTemperature']:.1f}°C  {data['uvDateTime']}"
        rect = font.getsize(state)
        surf.text((width - rect[0], 0), state, fill=text_color, font=font)
        surf.text((0, 0), text, fill=text_color, font=font)

        for col in range(cols):
            for row in range(rows):
                i = col + cols * row
                color = int(round(63 + step_color * (values[i] - data["uvMinValue"])))
                pos_x = col * step_x
                pos_y = text_size + (row * step_y)
                surf.rectangle(((pos_x, pos_y), (pos_x + step_x, pos_y + step_y)), (0, 0, color))

                val = str(int(values[i]))
                rect = font.getsize(val)
                offset_x = int((step_x - rect[0]) / 2)
                offset_y = int((step_y - rect[1]) / 2)
                surf.text((pos_x + offset_x, pos_y + offset_y), val, fill=text_color, font=font)

                val = f"{perc[i]:+.1f} %"
                rect = font_small.getsize(val)
                offset_x = int((step_x - rect[0]) / 2)
                surf.text(
                    (pos_x + offset_x, pos_y + offset_y + text_size),
                    val,
                    fill=perc_minus_color if perc[i] < 0 else perc_plus_color,
                    font=font_small,
                )

        image.save(filename)
