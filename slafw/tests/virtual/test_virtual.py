# This file is part of the SLA firmware
# Copyright (C) 2020 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import threading
import unittest
from multiprocessing import Process
from threading import Thread
from time import sleep

import psutil
import pydbus
from dbusmock import DBusTestCase
from gi.repository import GLib
from psutil import NoSuchProcess

from slafw.api.printer0 import Printer0State
from slafw.tests.mocks.dbus.filemanager0 import FileManager0
from slafw.tests.mocks.dbus.hostname import Hostname
from slafw.tests.mocks.dbus.networkmanager import NetworkManager
from slafw.tests.mocks.dbus.timedate import TimeDate
from slafw.virtual import run_virtual


class TestVirtualPrinter(DBusTestCase):
    dbus_mocks = []
    event_loop = GLib.MainLoop()
    event_thread: threading.Thread = None

    def setUp(self) -> None:
        super().setUp()
        self.started_ok = False
        self.dbus_mocks = []

    @classmethod
    def setUpClass(cls):
        cls.start_system_bus()
        cls.dbus_con = cls.get_dbus(system_bus=True)

    def tearDown(self):
        for dbus_mock in self.dbus_mocks:
            dbus_mock.unpublish()
        super().tearDown()

    def run_virtual_without_system(self):
        # Setup common system services
        bus = pydbus.SystemBus()
        nm = NetworkManager()
        self.dbus_mocks = [
            bus.publish(FileManager0.__INTERFACE__, FileManager0()),
            bus.publish(
                NetworkManager.__INTERFACE__, nm, ("Settings", nm), ("test1", nm), ("test2", nm), ("test3", nm),
            ),
            bus.publish(Hostname.__INTERFACE__, Hostname()),
            bus.publish(TimeDate.__INTERFACE__, TimeDate()),
        ]
        run_virtual()

    def test_virtual(self):
        virtual = Process(target=self.run_virtual_without_system)
        virtual.start()

        # Wait for virtual printer to start
        for i in range(30):
            print(f"Attempt {i} to verify virtual printer is running")
            sleep(1)
            # Run checks in threads as the calls might block
            Thread(target=self.run_check, daemon=True).start()
            if self.started_ok or not virtual.is_alive():
                break

        children = psutil.Process().children(recursive=True)
        print("### Terminating virtual printer")
        virtual.terminate()
        sleep(1)
        for child in children:
            try:
                child.terminate()
                print(f"Terminated child: {child.pid}")
            except NoSuchProcess:
                pass  # Possibly the child was gracefully terminated
        print("### Killing virtual printer")
        virtual.kill()
        for child in children:
            try:
                child.kill()
                print(f"Killed child: {child.pid}")
            except NoSuchProcess:
                pass  # Possibly the child was gracefully terminated
        virtual.join()

        self.assertTrue(self.started_ok, "Virtual printer idle on DBus")

    def run_check(self):
        try:
            printer0 = pydbus.SystemBus().get("cz.prusa3d.sl1.printer0")
            state = Printer0State(printer0.state)
            print(f"Printer state on Dbus: {state}")
            if state == Printer0State.IDLE:
                print("Printer is up and running")
                self.started_ok = True

        except GLib.Error as e:
            print("Attempt to obtain virtual printer state ended up with exception: %s", e)


if __name__ == "__main__":
    unittest.main()
