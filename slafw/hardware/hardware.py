# This file is part of the SLA firmware
# Copyright (C) 2022-2024 Prusa Research a.s - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
from abc import abstractmethod
from functools import cached_property, lru_cache
from time import sleep
from typing import Dict

import bitstring
import distro
import pydbus
from PySignal import Signal

from slafw import defines
from slafw.configs.hw import HwConfig
from slafw.configs.unit import Ms, Ustep
from slafw.exposure.profiles import SingleLayerProfileSL1
from slafw.hardware.axis import Axis
from slafw.hardware.exposure_screen import ExposureScreen
from slafw.hardware.fan import Fan
from slafw.hardware.temp_sensor import TempSensor
from slafw.hardware.uv_led import UVLED
from slafw.hardware.power_led import PowerLed
from slafw.hardware.printer_model import PrinterModelBase
from slafw.hardware.tilt import Tilt
from slafw.hardware.tower import Tower


class BaseHardware:
    # pylint: disable = too-many-instance-attributes
    # pylint: disable = too-many-public-methods
    uv_led: UVLED
    tilt: Tilt
    tower: Tower
    uv_led_fan: Fan
    blower_fan: Fan
    rear_fan: Fan
    uv_led_temp: TempSensor
    ambient_temp: TempSensor
    cpu_temp: TempSensor
    exposure_screen: ExposureScreen
    power_led: PowerLed

    def __init__(self, hw_config: HwConfig, printer_model: PrinterModelBase):
        self.logger = logging.getLogger(__name__)
        self.config = hw_config
        self.printer_model = printer_model

        self.resin_sensor_state_changed = Signal()
        self.cover_state_changed = Signal()
        self.power_button_state_changed = Signal()
        self.mc_sw_version_changed = Signal()
        self.tower_position_changed = Signal()
        self.tilt_position_changed = Signal()

    @cached_property
    def fans(self) -> Dict[int, Fan]:
        return {
            0: self.uv_led_fan,
            1: self.blower_fan,
            2: self.rear_fan,
        }

    # MC stores axes in bitmap. Keep it same. Tower 1, Tilt 2
    @cached_property
    def axes(self) -> Dict[int, Axis]:
        return {
            1: self.tower,
            2: self.tilt,
        }

    def start_fans(self):
        for fan in self.fans.values():
            fan.running = True

    def stop_fans(self):
        for fan in self.fans.values():
            fan.running = False

    @abstractmethod
    def connect(self):
        """
        connect to MC and init all hw components
        """

    @abstractmethod
    def start(self):
        """
        init default values
        """

    @property
    def system_version(self) -> str:
        """Return a semver OS version of the image as string."""
        return distro.os_release_attr("version").split(" ")[0]

    @property
    def system_name(self) -> str:
        """Return an OS name of the image as string."""
        return distro.name()

    @property
    def cpuSerialNo(self):
        return self.read_cpu_serial()[0]

    @property
    def isKit(self):
        return self.read_cpu_serial()[1]

    @property
    def ethMac(self):
        return self.read_cpu_serial()[2]

    @abstractmethod
    def beep(self, frequency_hz: int, length_s: float):
        ...

    def beepEcho(self) -> None:
        self.beep(1800, 0.05)

    def beepRepeat(self, count):
        for _ in range(count):
            self.beep(1800, 0.1)
            sleep(0.5)

    def beepAlarm(self, count):
        for _ in range(count):
            self.beep(1900, 0.05)
            sleep(0.25)

    def checkFailedBoot(self):
        """
        Check for failed boot by comparing current and last boot slot

        :return: True is last boot failed, false otherwise
        """
        try:
            # Get slot statuses
            rauc = pydbus.SystemBus().get("de.pengutronix.rauc", "/")["de.pengutronix.rauc.Installer"]
            status = rauc.GetSlotStatus()

            a = "no-data"
            b = "no-data"

            for slot, data in status:
                if slot == "rootfs.0":
                    a = data["boot-status"]
                elif slot == "rootfs.1":
                    b = data["boot-status"]

            self.logger.info("Slot A boot status: %s", a)
            self.logger.info("Slot B boot status: %s", b)

            if a == "good" and b == "good":
                # Device is booting fine, remove stamp
                if defines.bootFailedStamp.is_file():
                    defines.bootFailedStamp.unlink()

                return False

            self.logger.error("Detected broken boot slot !!!")
            # Device has boot problems
            if defines.bootFailedStamp.is_file():
                # The problem is already reported
                return False

            # This is a new problem, create stamp, report problem
            defines.bootFailedStamp.parent.mkdir(parents=True, exist_ok=True)
            defines.bootFailedStamp.touch(exist_ok=True)
            return True

        except Exception:
            self.logger.exception("Failed to check for failed boot")
            # Something went wrong during check, expect the worst
            return True

    @lru_cache(maxsize=1)
    def read_cpu_serial(self):
        # pylint: disable = too-many-locals
        ot = {0: "CZP"}
        sn = "*INVALID*"
        mac_hex = "*INVALID*"
        is_kit = True  # kit is more strict
        try:
            with open(defines.cpuSNFile, "rb") as nvmem:
                s = bitstring.BitArray(bytes=nvmem.read())

            # pylint: disable = unbalanced-tuple-unpacking
            # pylint does not understand tuples passed by bitstring
            mac, mcs1, mcs2, snbe = s.unpack("pad:192, bits:48, uint:8, uint:8, pad:224, uintbe:64")
            mcsc = mac.count(1)
            if mcsc != mcs1 or mcsc ^ 255 != mcs2:
                self.logger.error("MAC checksum FAIL (is %02x:%02x, should be %02x:%02x)", mcs1, mcs2, mcsc, mcsc ^ 255)
            else:
                mac_hex = ":".join(mac.hex[i:i+2] for i in range(0, len(mac.hex), 2))
                self.logger.info("MAC: %s (checksum %02x:%02x)", mac_hex, mcs1, mcs2)

                # byte order change
                # pylint: disable = unbalanced-tuple-unpacking
                # pylint does not understand tuples passed by bitstring
                sn = bitstring.BitArray(length=64, uintle=snbe)

                scs2, scs1, snnew = sn.unpack("uint:8, uint:8, bits:48")
                scsc = snnew.count(1)
                if scsc != scs1 or scsc ^ 255 != scs2:
                    self.logger.warning(
                        "SN checksum FAIL (is %02x:%02x, should be %02x:%02x), getting old SN format",
                        scs1,
                        scs2,
                        scsc,
                        scsc ^ 255,
                    )
                    sequence_number, is_kit, ean_pn, year, week, origin = sn.unpack(
                        "pad:14, uint:17, bool, uint:10, uint:6, pad:2, uint:6, pad:2, uint:4"
                    )
                    prefix = "*"
                else:
                    sequence_number, is_kit, ean_pn, year, week, origin = snnew.unpack(
                        "pad:4, uint:17, bool, uint:10, uint:6, uint:6, uint:4"
                    )
                    prefix = ""

                sn = f"{prefix:s}{ot.get(origin, 'UNK'):3s}X{week:02d}{year:02d}X{ean_pn:03d}X" \
                     f"{'K' if is_kit else 'C':s}{sequence_number:05d}"
                self.logger.info("SN: %s", sn)

        except Exception:
            self.logger.exception("CPU serial:")

        return sn, is_kit, mac_hex

    @cached_property
    def emmc_serial(self) -> str:  # pylint: disable = no-self-use
        return defines.emmc_serial_path.read_text(encoding="ascii").strip()

    @staticmethod
    def _count_move_time(axis: Axis, length: Ustep, steprate: int) -> Ms:
        # sla-fw checks every 0.1 s if axis is still moving. See: Axis._wait_to_stop_delay. Additional 0.021 s is
        # measured average delay of the system. Thus, the axis movement time is always quantized by this value.
        delay = 0.121

        # Both axes use linear ramp movements. This factor compensates the tilt acceleration and deceleration time.
        tilt_comp_factor = 0.1

        # Both axes use linear ramp movements. This factor compensates the tower acceleration and deceleration time.
        tower_comp_factor = 20000

        if length and steprate:
            l = int(length)
            result = Ms((int(l / (steprate * delay) + tilt_comp_factor) + 1) * (delay * 1000))
            if axis.name == "tower":
                result = Ms((int(l / (steprate * delay) + (steprate + l) / tower_comp_factor) + 1) * (delay * 1000))
            return result
        return Ms(0)

    def layer_peel_move_time(self, layer_height_nm: int, p: SingleLayerProfileSL1) -> int:
        profile_change_delay = Ms(20) # propagation delay of sending profile change command to MC
        sleep_delay = Ms(2) # average delay of the Linux system sleep function
        tilt = Ms(0)
        if p.use_tilt:
            tilt += profile_change_delay
            # initial down movement
            tilt += self._count_move_time(
                self.tilt,
                p.tilt_down_offset_steps,
                self.tilt.profiles[p.tilt_down_initial_profile].maximum_steprate
            )
            # initial down delay
            tilt += p.tilt_down_offset_delay_ms + sleep_delay
            # profile change delay if down finish profile is different from down initial
            tilt += profile_change_delay
            # cycle down movement
            tilt += p.tilt_down_cycles * self._count_move_time(
                self.tilt,
                (self.config.tiltHeight - p.tilt_down_offset_steps) // p.tilt_down_cycles,
                self.tilt.profiles[p.tilt_down_finish_profile].maximum_steprate
            )
            # cycle down delay
            tilt += p.tilt_down_cycles * (p.tilt_down_delay_ms + sleep_delay)

            # profile change delay if up initial profile is different from down finish
            tilt += profile_change_delay
            # initial up movement
            tilt += self._count_move_time(
                self.tilt,
                self.config.tiltHeight - p.tilt_up_offset_steps,
                self.tilt.profiles[p.tilt_up_initial_profile].maximum_steprate
            )
            # initial up delay
            tilt += p.tilt_up_offset_delay_ms + sleep_delay
            # profile change delay if up initial profile is different from down finish
            tilt += profile_change_delay
            # finish up movement
            tilt += p.tilt_up_cycles * self._count_move_time(
                self.tilt,
                p.tilt_up_offset_steps // p.tilt_up_cycles,
                self.tilt.profiles[p.tilt_up_finish_profile].maximum_steprate
            )
            # cycle down delay
            tilt += p.tilt_up_cycles * (p.tilt_up_delay_ms + sleep_delay)

        tower = Ms(0)
        if p.tower_hop_height_nm:
            tower += self._count_move_time(
                self.tower,
                self.config.nm_to_tower_microsteps(int(p.tower_hop_height_nm) + layer_height_nm),
                self.tower.profiles[p.tower_profile].maximum_steprate
            )
            tower += self._count_move_time(
                self.tower,
                self.config.nm_to_tower_microsteps(int(p.tower_hop_height_nm)),
                self.tower.profiles[p.tower_profile].maximum_steprate
            )
            tower += profile_change_delay
        else:
            tower += self._count_move_time(
                self.tower,
                self.config.nm_to_tower_microsteps(layer_height_nm),
                self.tower.profiles[p.tower_profile].maximum_steprate
            )
            tower += profile_change_delay
        self.logger.debug("layer peel time: %f", tilt + tower)
        return int(tilt + tower)

    @abstractmethod
    def exit(self):
        ...

    @abstractmethod
    def motors_release(self) -> None:
        """
        Disables all stepper motors
        """

    @abstractmethod
    def getResinSensorState(self) -> bool:
        """
        TODO: Create component for this one
        """

    @abstractmethod
    def isCoverClosed(self, check_for_updates: bool = True) -> bool:
        """
        TODO: Create component for this one
        """

    @abstractmethod
    def isCoverVirtuallyClosed(self, check_for_updates: bool = True) -> bool:
        """
        TODO: Create component for this one
        """

    @abstractmethod
    def getPowerswitchState(self) -> bool:
        """
        TODO: Create component for this one
        """

    @property
    @abstractmethod
    def mcFwVersion(self):
        """
        TODO: Create component for this one
        """

    @property
    @abstractmethod
    def mcFwRevision(self):
        """
        TODO: Create component for this one
        """

    @property
    @abstractmethod
    def mcBoardRevision(self):
        """
        TODO: Create component for this one
        """

    @property
    @abstractmethod
    def mcSerialNo(self) -> str:
        """
        TODO: Create component for this one
        """

    @abstractmethod
    def eraseEeprom(self):
        """
        TODO: Create component for this one
        """

    @abstractmethod
    async def get_resin_sensor_position_mm(self) -> float:
        """
        TODO: Create component for this one
        """

    @abstractmethod
    async def get_resin_volume_async(self) -> float:
        """
        TODO: Create component for this one
        """

    @abstractmethod
    def flashMC(self):
        """
        TODO: Create component for this one
        """

    @abstractmethod
    def initDefaults(self):
        """
        TODO: Create component for this one
        """

    @abstractmethod
    def resinSensor(self, state: bool):
        """
        TODO: Create component for this one
        """

    @staticmethod
    @abstractmethod
    def calcPercVolume(volume_ml: float) -> int:
        """
        TODO: Create component for this one
        """
