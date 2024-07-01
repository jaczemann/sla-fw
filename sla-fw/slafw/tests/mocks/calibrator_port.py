# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2020 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import datetime
from queue import Queue
from time import sleep

from slafw import test_runtime


class Serial:
    def __init__(self):
        self._data = Queue()
        self._error_cnt = 0
        self._connect()

    def _connect(self):
        self._data.put("<done".encode())

    def open(self):
        pass

    @property
    def is_open(self):
        return True

    def close(self):
        pass

    def write(self, data):
        if data == b">all\n":
            self._data.put(data)
            if (
                test_runtime.uv_on_until
                and test_runtime.uv_on_until > datetime.now()
                and not test_runtime.exposure_image.is_screen_black
            ):
                intensity = self._intensity_response(test_runtime.uv_pwm)
            else:
                intensity = 0
            response = "<" + ",".join([str(intensity) for _ in range(60)]) + ",347"
            self._data.put(response.encode())

    def read(self):
        raise NotImplementedError()

    def readline(self):
        self._simulate_error()
        sleep(0.1)
        return self._data.get()

    def _simulate_error(self):
        if not test_runtime.uv_error_each:
            return

        self._error_cnt += 1
        if self._error_cnt > test_runtime.uv_error_each:
            self._error_cnt = 0
            self._data.put("<done".encode())
            raise IOError("Injected error")

    def inWaiting(self):
        return self._data.qsize()

    @staticmethod
    def _intensity_response(pwm) -> float:
        # Linear response
        # 140 intensity at 200 PWM
        return 140 * pwm / 200
