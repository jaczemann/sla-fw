# This file is part of the SLA firmware
# Copyright (C) 2023 Prusa Research a.s - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later


import logging

import socket
from abc import ABC, abstractmethod
from dataclasses import dataclass
from re import Pattern
from threading import Thread, Lock
from time import sleep
from typing import Optional, Callable, List, Any

import serial
from evdev import UInput

from slafw import defines
from slafw.motion_controller.queue_stream import QueueStream
from slafw.motion_controller.states import CommError
from slafw.errors.errors import MotionControllerException, \
    MotionControllerNotResponding, MotionControllerWrongResponse
from slafw.motion_controller.trace import LineTrace, LineMarker, Trace
from slafw.functions.decorators import safe_call


@dataclass
class Board:
    revision: int = -1
    subRevision: str = "*INVALID*"
    serial: str = "*INVALID*"


@dataclass
class Fw:
    version: str = "*INVALID*"
    revision: int = -1


class MotionControllerBase(ABC):
    # pylint: disable=too-many-instance-attributes
    # pylint: disable=too-many-public-methods

    HISTORY_DEPTH = 30

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.trace = Trace(self.HISTORY_DEPTH)
        self.fw = Fw()
        self.board = Board()
        self._read_stream = QueueStream(self.READ_QUEUE_TIMEOUT)
        self._raw_read_lock = Lock()
        self._command_lock = Lock()
        self._exclusive_lock = Lock()
        self._flash_lock = Lock()

        self._port = serial.Serial()
        self._port.port = self.PORT
        self._port.baudrate = self.BAUD_RATE_NORMAL
        self._port.timeout = self.READ_QUEUE_TIMEOUT
        self._port.writeTimeout = self.READ_QUEUE_TIMEOUT
        self._port.bytesize = 8
        self._port.parity = "N"
        self._port.stopbits = 1
        self._port.xonxoff = False
        self._port.rtscts = False
        self._port.dsrdtr = False
        self._port.interCharTimeout = None

        self._value_refresh_thread = Thread(target=self._value_refresh_body, daemon=True)

        self._debug_sock: Optional[socket.socket] = None
        self._debug_thread: Optional[Thread] = None
        self._u_input: Optional[UInput] = None

    @property
    @abstractmethod
    def PORT(self) -> str:
        """
        string with path to serial device /dev/tty...
        """

    @property
    @abstractmethod
    def REQUIRED_VERSION(self) -> str:
        """
        version of MC FW. If does not match MC is flashed at start.
        """

    @property
    @abstractmethod
    def BAUD_RATE_NORMAL(self) -> int:
        """
        baud speed of FW
        """

    @property
    @abstractmethod
    def BAUD_RATE_BOOTLOADER(self) -> int:
        """
        baud speed of bootloader
        """

    @property
    @abstractmethod
    def READ_QUEUE_TIMEOUT(self) -> int:
        """
        read stream queue timeout [s]
        """

    @property
    @abstractmethod
    def commOKStr(self) -> Pattern:
        """
        regexp at the end of message.
        """

    @property
    @abstractmethod
    def commErrStr(self) -> Pattern:
        """
        error regexp
        """

    @abstractmethod
    def open(self):
        """
        Open serial connection to MCU and start reading thread.
        On SL1 initiates uinput on power button
        """

    def __del__(self):
        self.exit()

    def exit(self):
        """
        Closes serial port, joins reading thread, value refresh thread
        """
        if self.is_open:
            self._port.close()
        if self._u_input:
            self._u_input.close()
        if self._value_refresh_thread.is_alive():
            while not self._value_refresh_task:
                sleep(0.1)
            self._value_refresh_task.cancel()
            self._value_refresh_thread.join()

    def _port_read_thread(self):
        """
        Body of a thread responsible for reading data from serial port

        This reads everything from serial and
           - Stores it in a queue stream for later use
           - Sends it to the debugger
        """
        while self._port.is_open:
            with self._raw_read_lock:
                try:
                    data = self._port.read()
                except serial.SerialTimeoutException:
                    data = b""
            if data:
                self._read_stream.put(data)
                self._debug_send(data)

    def in_waiting(self) -> bool:
        return self._read_stream.waiting()

    @property
    def is_open(self) -> bool:
        return self._port.is_open if self._port else False

    def _read_port(self, garbage=False) -> bytes:
        """
        Read raw line from motion controller

        :param garbage: Whenever to mark line read as garbage in command trace
        :return: Line read as raw bytes
        """
        marker = LineMarker.GARBAGE if garbage else LineMarker.INPUT
        ret = self._read_stream.readline()
        trace = LineTrace(marker, ret)
        self.trace.append_trace(trace)
        return ret

    def read_port_text(self, garbage=False) -> str:
        """
        Read line from serial as stripped decoded text

        :param garbage: Mark this data as garbage. Line will be marked as such in trace
        :return: Line read from motion controller
        """
        return self._read_port(garbage=garbage).decode("ascii").strip()

    def write_port(self, data: bytes) -> int:
        """
        Write data to a motion controller

        :param data: Data to be written
        :return: Number of bytes written
        """
        self.trace.append_trace(LineTrace(LineMarker.OUTPUT, data))
        self._debug_send(bytes(LineMarker.OUTPUT) + data)
        return self._port.write(data)

    def start_debugging(self, bootloader: bool) -> None:
        """
        Starts debugger thread

        :param bootloader: True for bootloader mode, False for user mode
        :return: None
        """
        self._debug_thread = Thread(target=self._debug, args=(bootloader,))
        self._debug_thread.start()

    def _debug(self, bootloader: bool) -> None:
        """
        Debugging thread body

        This runs the debugging session. Initially this thread waits for debugger connection
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("0.0.0.0", defines.mc_debug_port))
            self.logger.info("Listening for motion controller debug connection")
            s.listen(1)
            self._debug_sock, address = s.accept()
            self.logger.info("Debug connection accepted from %s", address)

            if bootloader:
                self._debug_bootloader()
            else:
                self._debug_user()

            self.logger.info("Terminating debugging session on client disconnect")
            self._debug_sock = None
            s.close()
            self._port.baudrate = self.BAUD_RATE_NORMAL
            self.logger.info("Debugging session terminated")

            if bootloader:
                # A custom firmware was uploaded, lets reconnect with version check disabled
                self.connect(False)

    def _debug_bootloader(self):
        self.logger.info("Starting bootloader debugging session")
        with self._exclusive_lock:
            self._port.baudrate = self.BAUD_RATE_BOOTLOADER
            self.reset()

            while True:
                data = self._debug_sock.recv(1)
                if not data:
                    break
                self._port.write(data)

    def _debug_user(self):
        self.logger.info("Starting normal debugging session")
        self._debug_sock.sendall(b"\n\n\n>>> Debugging session started, command history: <<<\n\n\n")
        self._debug_sock.sendall(bytes(self.trace))
        self._debug_sock.sendall(b"\n\n\n>>> Type #stop for exclusive mode <<<\n\n\n")

        with self._debug_sock.makefile("rb") as f:
            while True:
                line = f.readline()
                if not line:
                    break
                if line.startswith(b"#stop"):
                    self.logger.info("Starting exclusive debugging")
                    if not self._exclusive_lock.locked():
                        self.logger.debug("Switching to exclusive debugging")
                        self._exclusive_lock.acquire()  # pylint: disable = consider-using-with
                        self._debug_sock.sendall(b"\n\n\n>>> Now in exclusive mode type #cont to leave it <<<\n\n\n")
                    else:
                        self._debug_sock.sendall(b"\n\n\n>>> Exclusive mode already enabled <<<\n\n\n")

                elif line.startswith(b"#cont"):
                    self.logger.info("Stopping exclusive debugging")
                    if self._exclusive_lock.locked():
                        self.logger.debug("Switching to normal debugging")
                        self._exclusive_lock.release()
                        self._debug_sock.sendall(b"\n\n\n>>> Now in normal mode <<<\n\n\n")
                    else:
                        self._debug_sock.sendall(b"\n\n\n>>> Already in normal mode, do action <<<\n\n\n")
                else:
                    with self._command_lock:
                        self.logger.debug("Passing user command: %s", line)
                        self._port.write(line)
            if self._exclusive_lock.locked():
                self._exclusive_lock.release()

    def _debug_send(self, data: bytes):
        if self._debug_sock:
            try:
                self._debug_sock.sendall(data)
            except BrokenPipeError:
                self.logger.exception("Attempt to send data to broken debug socket")

    @abstractmethod
    def connect(self, mc_version_check: bool = True) -> None:
        """
        Open serial port, check MC revison and version, start value checker
        """

    def _read_garbage(self) -> None:
        """
        Reads initial garbage/comments found in port.

        This assumes portlock is already taken

        Random garbage/leftovers signal an error. Lines starting with comment "#" are considered debug output of the
        motion controller code. Those produced by asynchronous commands (like tilt/tower home) end up here.
        """
        while self.in_waiting():
            try:
                line = self._read_port(garbage=True)
                if line.startswith(b"#"):
                    self.logger.debug("Comment in MC port: %s", line)
                else:
                    self.logger.warning("Garbage pending in MC port: %s", line)
            except (serial.SerialException, UnicodeError) as e:
                raise MotionControllerException("Failed garbage read", self.trace) from e

    def do(self, cmd, *args, return_process: Callable = lambda x: x) -> Any:
        with self._exclusive_lock, self._command_lock:
            if self._flash_lock.acquire(blocking=False):  # pylint: disable = consider-using-with
                try:
                    self._read_garbage()
                    self.do_write(cmd, *args)
                    return self.do_read(return_process=return_process)
                finally:
                    self._flash_lock.release()
            else:
                raise MotionControllerException("MC flash in progress", self.trace)

    def do_write(self, cmd, *args) -> None:
        """
        Write command

        :param cmd: Command string
        :param args: Command arguments
        :return: None
        """
        cmd_string = " ".join(str(x) for x in (cmd,) + args)
        try:
            self.write_port(f"{cmd_string}\n".encode("ascii"))
        except serial.SerialTimeoutException as e:
            raise MotionControllerException(f"Timeout writing serial port: {cmd_string}", self.trace) from e

    def do_read(self, return_process: Callable) -> Any:
        """
        Read until some response is received

        :return: Processed MC response
        """
        while True:
            try:
                line = self.read_port_text()
            except Exception as e:
                raise MotionControllerNotResponding("Failed to read line from MC", self.trace) from e

            ok_match = self.commOKStr.match(line)

            if ok_match is not None:
                response = ok_match.group(1).strip() if ok_match.group(1) else ""
                try:
                    return return_process(response)
                except Exception as e:
                    raise MotionControllerWrongResponse("Failed to process MC response", self.trace) from e

            err_match = self.commErrStr.match(line)
            if err_match is not None:
                try:
                    err_code = int(err_match.group(1))
                except ValueError:
                    err_code = 0
                err = CommError(err_code).name
                self.logger.error("error: '%s'", err)
                raise MotionControllerException(f"MC command failed with error: {err}", self.trace)

            if line.startswith("#"):
                self.logger.debug("Received comment response: %s", line)
            else:
                raise MotionControllerException("MC command resulted in non-response line", self.trace)

    @abstractmethod
    def soft_reset(self) -> None:
        """
        Software reset of MCU. Eg "!rst" on SL1.
        """

    @abstractmethod
    def _ensure_ready(self, after_soft_reset=False) -> None:
        """
        Ensure MC is ready after reset/flash
        This assumes portLock to be already acquired
        """

    @abstractmethod
    def flash(self) -> None:
        """
        Flash MCU with current FW.
        """

    @abstractmethod
    def reset(self) -> None:
        """
        Does a hard reset of the motion controller.
        Assumes portLock is already acquired
        """

    @safe_call(False, MotionControllerException)
    @abstractmethod
    def checkState(self, name, check_for_updates: bool = True):
        """
        Get state from state bits by name
        """

    @abstractmethod
    def _handle_updates(self, state_bits: List[bool]):
        """
        Emit signals on status change
        """

    @abstractmethod
    def _value_refresh_body(self):
        """
        Thread to run Value checkers
        """

    @abstractmethod
    async def _value_refresh(self):
        """
        Method defines all checks needed and actually runs them by asyncio.gather
        """
