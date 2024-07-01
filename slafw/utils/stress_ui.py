# This file is part of the SLA firmware
# Copyright (C) 2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from threading import Thread
from time import sleep

import pydbus
from gi.repository import GLib

from slafw.api.exposure0 import Exposure0
from slafw.api.printer0 import Printer0
from slafw.hardware.printer_model import PrinterModel
from slafw.states.exposure import ExposureState
from slafw.tests.mocks.exposure import Exposure
from slafw.tests.mocks.printer import Printer
from slafw.tests.mocks.hardware import HardwareMock
from slafw.tests.mocks.action_manager import ActionManager

bus = pydbus.SystemBus()

exposure = Exposure()
printer = Printer(HardwareMock(printer_model=PrinterModel.SL1), ActionManager(exposure))

bus.publish(Printer0.__INTERFACE__, Printer0(printer))
bus.publish(Exposure0.__INTERFACE__, (Exposure0.dbus_path(exposure.data.instance_id), Exposure0(exposure)))

Thread(target=GLib.MainLoop().run, daemon=True).start()  # type: ignore[attr-defined]

while True:
    for state in ExposureState:
        sleep(0.5)
        print(f"Setting exposure state to {state}")
        exposure.set_state(state)
