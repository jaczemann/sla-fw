# This file is part of the SLA firmware
# Copyright (C) 2018-2023 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio
import re
import subprocess
from asyncio import CancelledError, Task
from threading import Thread
from time import sleep
from typing import List, Tuple, Optional

from gpiod import chip, line_request, find_line
from PySignal import Signal
from evdev import UInput, ecodes

from slafw import defines
from slafw.motion_controller.base_controller import MotionControllerBase
from slafw.motion_controller.states import (
    ResetFlags,
    StatusBits,
)
from slafw.errors.errors import MotionControllerException, MotionControllerWrongRevision, MotionControllerWrongFw
from slafw.motion_controller.trace import LineTrace, LineMarker
from slafw.motion_controller.value_checker import ValueChecker, UpdateInterval
from slafw.functions.decorators import safe_call


class MotionControllerSL1(MotionControllerBase):
    # pylint: disable=too-many-instance-attributes

    BAUD_RATE_NORMAL = 115200
    BAUD_RATE_BOOTLOADER = 19200
    READ_QUEUE_TIMEOUT = 3
    TEMP_UPDATE_INTERVAL_S = 3
    FAN_UPDATE_INTERVAL_S = 3
    PORT = "/dev/ttyS2"
    REQUIRED_VERSION = "1.2.0"

    commOKStr = re.compile("^(.*)ok$")
    commErrStr = re.compile("^e(.)$")

    def __init__(self):
        super().__init__()
        self._reader_thread: Optional[Thread] = None
        self._old_state_bits: Optional[List[bool]] = None
        self._value_refresh_task: Optional[Task] = None

        self.tower_status_changed = Signal()
        self.tilt_status_changed = Signal()
        self.power_button_changed = Signal()
        self.cover_state_changed = Signal()
        self.value_refresh_failed = Signal()
        self.temps_changed = Signal()
        self.fans_rpm_changed = Signal()
        self.fans_error_changed = Signal()
        self.statistics_changed = Signal()

        self.power_button_changed.connect(self._power_button_handler)
        self.cover_state_changed.connect(self._cover_state_handler)

        self._fans_mask = {0: False, 1: False, 2: False}
        self._fans_rpm = {0: defines.fanMinRPM, 1: defines.fanMinRPM, 2: defines.fanMinRPM}

        # pylint: disable=no-member
        self._u_input = UInput(
            {ecodes.EV_KEY: [ecodes.KEY_CLOSE, ecodes.KEY_POWER]}, name="sl1-motioncontroller", version=0x1,
        )

    def open(self):
        if not self.is_open:
            self._port.open()

            if not self._reader_thread or not self._reader_thread.is_alive():
                self._reader_thread = Thread(target=self._port_read_thread, daemon=True)
                self._reader_thread.start()
        else:
            self._read_garbage()

    def connect(self, mc_version_check: bool = True) -> None:
        self.open()
        state = self.getStateBits(["fatal", "reset"], check_for_updates=False)
        if state["fatal"]:
            raise MotionControllerException("MC failed with fatal flag", self.trace)
        if state["reset"]:
            reset_bits = self.doGetBoolList("?rst", bit_count=8)
            bit = 0
            for val in reset_bits:
                if val:
                    self.logger.info("motion controller reset flag: %s", ResetFlags(bit).name)
                bit += 1
        tmp = self._get_board_revision()
        self.fw.revision = tmp[0]
        self.board.revision = divmod(tmp[1], 32)[1]
        self.board.subRevision = chr(divmod(tmp[1], 32)[0] + ord("a"))
        self.logger.info(
            "motion controller board revision: %d%s",
            self.board.revision,
            self.board.subRevision,
        )
        if self.board.revision != 6:
            raise MotionControllerWrongRevision(trace=self.trace)
        if self.fw.revision != self.board.revision:
            self.logger.warning(
                "Board and firmware revisions differ! Firmware: %d, board: %d!",
                self.fw.version,
                self.board.revision,
            )
            raise MotionControllerWrongFw(trace=self.trace)
        self.fw.version = self.do("?ver")
        self.logger.info("Motion controller firmware version: %s", self.fw.version)
        if mc_version_check:
            if self.fw.version != self.REQUIRED_VERSION:
                raise MotionControllerWrongFw(
                    message=f"Incorrect firmware, version {self.REQUIRED_VERSION} is required",
                    trace=self.trace
                )

        self.board.serial = self.do("?ser")
        if self.board.serial:
            self.logger.info("motion controller serial number: %s", self.board.serial)
        else:
            self.logger.warning("motion controller serial number is invalid")
            self.board.serial = "*INVALID*"

        # Value refresh thread
        self.temps_changed.emit(self._get_temperatures())  # Initial values for MC temperatures

        if self._value_refresh_thread and not self._value_refresh_thread.is_alive():
            self._value_refresh_thread.start()

    def doGetInt(self, *args):
        return self.do(*args, return_process=int)

    def doGetIntList(self, cmd, args=(), base=10, multiply: float = 1) -> List[int]:
        return self.do(cmd, *args, return_process=lambda ret: list([int(x, base) * multiply for x in ret.split(" ")]), )

    def doGetBool(self, cmd, *args):
        return self.do(cmd, *args, return_process=lambda x: x == "1")

    def doGetBoolList(self, cmd, bit_count, args=()) -> List[bool]:
        def process(data):
            bits = []
            num = int(data)
            for i in range(bit_count):
                bits.append(bool(num & (1 << i)))
            return bits

        return self.do(cmd, *args, return_process=process)

    def doGetHexedString(self, *args):
        return self.do(*args, return_process=lambda x: bytes.fromhex(x).decode("ascii"))

    def doSetBoolList(self, command, bits):
        bit = 0
        out = 0
        for val in bits:
            out |= 1 << bit if val else 0
            bit += 1
        self.do(command, out)

    def soft_reset(self) -> None:
        with self._exclusive_lock, self._command_lock:
            if self._flash_lock.acquire(blocking=False):  # pylint: disable = consider-using-with
                try:
                    self._read_garbage()
                    self.trace.append_trace(LineTrace(LineMarker.RESET, b"Motion controller soft reset"))
                    self.write_port("!rst\n".encode("ascii"))
                    self._ensure_ready(after_soft_reset=True)
                except Exception as e:
                    raise MotionControllerException("Reset failed", self.trace) from e
                finally:
                    self._flash_lock.release()
            else:
                raise MotionControllerException("MC flash in progress", self.trace)

    def _ensure_ready(self, after_soft_reset=False) -> None:
        """
        Ensure MC is ready after reset/flash
        This assumes portLock to be already acquired
        """
        try:
            mcusr = self.read_port_text()
            if after_soft_reset and self.commOKStr.match(mcusr):
                # This handles a bug in MC, !rst is sometimes not responded with ok. Correct solution is to ensure "ok"
                # is returned and handling soft reset as general command. This just eats the "ok" in case it is present.
                self.logger.debug("Detected \"ok\" instead of MCUSR, skipping")
                mcusr = self.read_port_text()
            self.logger.debug('"MCUSR..." read resulted in: "%s"', mcusr)
            ready = self.read_port_text()
            if ready != "ready":
                self.logger.info('"ready" read resulted in: "%s". Sleeping to ensure MC is ready.', ready)
                sleep(1.5)
                self._read_garbage()
        except Exception as e:
            raise MotionControllerException("Ready read failed", self.trace) from e

    def flash(self) -> None:
        with self._flash_lock:
            with self._raw_read_lock:
                self.reset()

                with subprocess.Popen(
                    [defines.script_dir / "flashMC.sh",
                     defines.firmwarePath,
                     self.PORT],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                ) as process:
                    while True:
                        line = process.stdout.readline()
                        retc = process.poll()
                        if line == "" and retc is not None:
                            break
                        if line:
                            line = line.strip()
                            if line == "":
                                continue
                            self.logger.info("flashMC output: '%s'", line)
                    if retc:
                        raise MotionControllerException(f"Flashing MC failed with code {retc}", self.trace)

            self._ensure_ready()

    def reset(self) -> None:
        """
        Does a hard reset of the motion controller.
        Assumes portLock is already acquired
        """
        self.logger.info("Doing hard reset of the motion controller")
        self.trace.append_trace(LineTrace(LineMarker.RESET, b"Motion controller hard reset"))
        rst = find_line("mc-reset")
        if not rst:
            self.logger.info("GPIO mc-reset not found")
            rst = chip(2).get_line(131)  # type: ignore[assignment]
        if not rst:
            raise MotionControllerException("Hard reset failed", self.trace)
        config = line_request()
        config.request_type = line_request.DIRECTION_OUTPUT
        rst.request(config)
        rst.set_value(1)
        sleep(1 / 1000000)
        rst.set_value(0)

    def getStateBits(self, request: List[str] = None, check_for_updates: bool = True):
        if not request:
            # pylint: disable = no-member
            request = StatusBits.__members__.keys()  # type: ignore

        bits = self.doGetBoolList("?", bit_count=16)
        if len(bits) != 16:
            raise ValueError(f"State bits count not match! ({bits})")

        if check_for_updates:
            self._handle_updates(bits)

        # pylint: disable = unsubscriptable-object
        return {name: bits[StatusBits.__members__[name.upper()].value] for name in request}

    @safe_call(False, MotionControllerException)
    def checkState(self, name, check_for_updates: bool = True):
        state = self.getStateBits([name], check_for_updates)
        return state[name]

    def _handle_updates(self, state_bits: List[bool]):
        # pylint: disable=no-member
        tower_idx = StatusBits.TOWER.value
        if not self._old_state_bits or state_bits[tower_idx] != self._old_state_bits[tower_idx]:
            self.tower_status_changed.emit(state_bits[tower_idx])
        tilt_idx = StatusBits.TILT.value
        if not self._old_state_bits or state_bits[tilt_idx] != self._old_state_bits[tilt_idx]:
            self.tilt_status_changed.emit(state_bits[tilt_idx])
        power_idx = StatusBits.BUTTON.value
        if not self._old_state_bits or state_bits[power_idx] != self._old_state_bits[power_idx]:
            self.power_button_changed.emit(state_bits[power_idx])
        cover_idx = StatusBits.COVER.value
        if not self._old_state_bits or state_bits[cover_idx] != self._old_state_bits[cover_idx]:
            self.cover_state_changed.emit(state_bits[cover_idx])
        fans_ids = StatusBits.FANS.value
        if not self._old_state_bits or state_bits[fans_ids] != self._old_state_bits[fans_ids]:
            self.fans_error_changed.emit(self.get_fans_error())
        self._old_state_bits = state_bits

    def _power_button_handler(self, state: bool):
        # pylint: disable=no-member
        self._u_input.write(ecodes.EV_KEY, ecodes.KEY_POWER, 1 if state else 0)
        self._u_input.syn()

    def _cover_state_handler(self, state: bool):
        # pylint: disable=no-member
        self._u_input.write(ecodes.EV_KEY, ecodes.KEY_CLOSE, 1 if state else 0)
        self._u_input.syn()

    def _get_board_revision(self):
        return self.doGetIntList("?rev")

    def _get_temperatures(self):
        temps = self.doGetIntList("?temp", multiply=0.1)
        if len(temps) != 4:
            raise ValueError(f"TEMPs count not match! ({temps})")

        return [round(temp, 1) for temp in temps]

    def _value_refresh_body(self):
        self.logger.info("Value refresh thread running")
        try:
            # Run refresh task
            asyncio.run(self._value_refresh())
        except CancelledError:
            pass  # This is normal printer shutdown
        except Exception:
            self.logger.exception("Value checker crashed")
            self.value_refresh_failed.emit()
            raise
        finally:
            self.logger.info("Value refresh checker ended")

    async def _value_refresh(self):
        checkers = [
            ValueChecker(
                self._get_temperatures, self.temps_changed, UpdateInterval.seconds(self.TEMP_UPDATE_INTERVAL_S)
            ),
            ValueChecker(self._get_fans_rpm, self.fans_rpm_changed, UpdateInterval.seconds(self.FAN_UPDATE_INTERVAL_S)),
            ValueChecker(self._get_statistics, self.statistics_changed, UpdateInterval.seconds(30)),
        ]
        checks = [checker.check() for checker in checkers]
        self._value_refresh_task = asyncio.gather(*checks)
        await self._value_refresh_task

    def set_fan_running(self, index: int, run: bool):
        self._fans_mask[index] = run
        self.doSetBoolList("!fans", self._fans_mask.values())

    def set_fan_rpm(self, index: int, rpm: int):
        self._fans_rpm[index] = rpm
        self.do("!frpm", " ".join([str(v) for v in self._fans_rpm.values()]))

    def _get_fans_rpm(self) -> Tuple[int, int, int]:
        rpms = self.doGetIntList("?frpm", multiply=1)
        if not rpms or len(rpms) != 3:
            raise MotionControllerException(f"RPMs count not match! ({rpms})")

        return rpms[0], rpms[1], rpms[2]

    def _get_statistics(self):
        data = self.doGetIntList("?usta")  # time counter [s] #TODO add uv average current, uv average temperature
        if len(data) != 2:
            raise ValueError(f"UV statistics data count not match! ({data})")

        return data

    @safe_call(False, (MotionControllerException, ValueError))
    def get_fan_running(self, index: int):
        return self.get_fans_bits("?fans", (index,))[index]

    @safe_call({0: True, 1: True, 2: True}, (MotionControllerException, ValueError))
    def get_fans_error(self, check_for_updates=False):
        state = self.getStateBits(["fans"], check_for_updates)
        if "fans" not in state:
            raise ValueError(f"'fans' not in state: {state}")

        return self.get_fans_bits("?fane", (0, 1, 2))

    def get_fans_bits(self, cmd, request):
        bits = self.doGetBoolList(cmd, bit_count=3)
        if len(bits) != 3:
            raise ValueError(f"Fans bits count not match! {bits}")

        return {idx: bits[idx] for idx in request}
