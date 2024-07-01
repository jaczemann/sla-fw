# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2020 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import re
from datetime import datetime, timedelta
from subprocess import Popen, PIPE, STDOUT
from time import monotonic_ns, sleep
from typing import Optional

from serial import SerialTimeoutException

from slafw import test_runtime


class Serial:
    TIMEOUT_MS = 3000

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.pwm_re = re.compile(b"!upwm ([0-9][0-9]*)\n")
        self.uled_re = re.compile(b"!uled ([01]) ([0-9][0-9]*)\n")
        self.process: Optional[Popen] = None
        self._is_open = False

    def open(self):
        self._is_open = True
        self.process = Popen(  # pylint: disable = consider-using-with
            ["SLA-control-01.elf"], stdin=PIPE, stdout=PIPE, stderr=STDOUT
        )
        mcusr = self.process.stdout.readline()
        self.logger.debug("MC serial simulator MCUSR = %s", mcusr)
        ready = self.process.stdout.readline()
        self.logger.debug("MC serial simulator ready = %s", ready)
        assert ready == b"ready\n"
        # Wait for MC sim to initialize
        # When asked directly after ready it tends to respond ?temp with 0,0,0,0
        sleep(0.2)

    @property
    def is_open(self) -> bool:
        return self._is_open

    def close(self):
        """
        Stop MS Port simulator
        Terminate simulator and output reading thread

        :return: None
        """
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=3)
            try:
                self.process.stdin.close()
            except BrokenPipeError:
                self.logger.exception("Failed to close stdin")
            try:
                self.process.stdout.close()
            except BrokenPipeError:
                self.logger.exception("Failed to close stderr")

            self._is_open = False

    def write(self, data: bytes):
        """
        Write data to simulated MC serial port

        :param data: Data to be written to simulated serial port
        :return: None
        """
        self.logger.debug("< %s", data)
        try:
            self.process.stdin.write(data)
            self.process.stdin.flush()
        except IOError:
            self.logger.exception("Failed to write to simulated port")

        # Decode UV PWM
        pwm_match = self.pwm_re.fullmatch(data)
        if pwm_match:
            try:
                test_runtime.uv_pwm = int(pwm_match.groups()[0].decode())
                self.logger.debug("UV PWM discovered: %d", test_runtime.uv_pwm)
            except (IndexError, UnicodeDecodeError, ValueError):
                self.logger.exception("Failed to decode UV PWM from MC data")

        # Decode UV LED state
        led_match = self.uled_re.fullmatch(data)
        if led_match:
            try:
                on = led_match.groups()[0].decode() == "1"
                duration_ms = int(led_match.groups()[1].decode())
                self.logger.debug("UV LED state discovered: %d %d", on, duration_ms)
                if on:
                    if duration_ms:
                        test_runtime.uv_on_until = datetime.now() + timedelta(milliseconds=duration_ms)
                    else:
                        test_runtime.uv_on_until = datetime.now() + timedelta(days=1)
                else:
                    test_runtime.uv_on_until = None
            except (IndexError, UnicodeDecodeError, ValueError):
                self.logger.exception("Failed to decode UV LED state from MC data")

    def read(self):
        """
        Read line from simulated serial port

        TODO: This pretends MC communication start has no weak places. In reality the MC "usually" starts before
              the libHardware. In such case the "start" is never actually read from MC. Therefore this also throws
              "start" away. In fact is may happen that the MC is initializing in paralel with the libHardware (resets)
              In such case the "start" can be read and libHardware will throw an exception. This is correct as
              working with uninitialized MC is not safe. Unfortunately we cannot wait for start/(future ready) as
              it may not come if the MC has initialized before we do so. Therefore we need to have a safe command
              that checks whenever the MC is ready.

        :return: Line read from simulated serial port
        """
        start_ns = monotonic_ns()

        while monotonic_ns() - start_ns < self.TIMEOUT_MS * 1000:
            # Unfortunately, there is no way how to make readline not block
            try:
                line = self.process.stdout.readline()
            except ValueError:
                break
            if line:
                self.logger.debug("> %s", line)
                return line
            sleep(0.001)
        raise SerialTimeoutException("Nothing to read from serial port")

    def inWaiting(self):
        raise NotImplementedError()

    def readline(self):
        raise NotImplementedError()
