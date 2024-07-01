# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from slafw.hardware.power_led import PowerLed

class WarningAction:
    def __init__(self, pwLed: PowerLed):
        self._pwLed = pwLed

    def __enter__(self):
        self._pwLed.set_warning()

    def __exit__(self, *_):
        self._pwLed.remove_warning()

class ErrorAction:
    def __init__(self, pwLed: PowerLed):
        self._pwLed = pwLed

    def __enter__(self):
        self._pwLed.set_error()

    def __exit__(self, *_):
        self._pwLed.remove_error()
