# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Tuple, List, Dict, Any

from pydbus.generic import signal
from pydbus import Variant

from slafw.api.decorators import dbus_api, auto_dbus


@dbus_api
class Rauc:
    __OBJECT__ = "de.pengutronix.rauc"
    __INTERFACE__ = "de.pengutronix.rauc.Installer"

    PropertiesChanged = signal()

    @auto_dbus
    @property
    def Operation(self) -> str:
        return "idle"

    @auto_dbus
    @property
    def Progress(self) -> Tuple[int, str, int]:
        return 0, "", 0

    @auto_dbus
    @property
    def BootSlot(self) -> str:
        return "A"

    @auto_dbus
    @property
    def Compatible(self) -> str:
        return "prusa64-sl1--prusa"

    @auto_dbus
    @property
    def LastError(self) -> str:
        return ""

    @auto_dbus
    def GetSlotStatus(self) -> List[Tuple[str, Dict[str, Any]]]: # pylint: disable=no-self-use
        return [
            (
                "rootfs.0",
                {
                    "status": Variant("s", "ok"),
                    "bootname": Variant("s", "A"),
                    "bundle.build": Variant("s", "20190613111424"),
                    "bundle.version": Variant("s", "1.0"),
                    "bundle.compatible": Variant("s", "prusa64-sl1--prusa"),
                    "activated.count": Variant("i", 11),
                    "description": Variant("s", ""),
                    "installed.timestamp": Variant("s", "2019-06-17T13:45:20Z"),
                    "class": Variant("s", "rootfs"),
                    "boot-status": Variant("s", "good"),
                    "state": Variant("s", "booted"),
                    "bundle.description": Variant("s", "sla-update-bundle version 1.0-r0"),
                    "installed.count": Variant("i", 11),
                    "device": Variant("s", "/dev/mmcblk2p2"),
                    "sha256": Variant("s", "1b7ad103c7f1216f351b93cd384ce5444288e6adb53ed40b81bd987b591fcbd1"),
                    "type": Variant("s", "ext4"),
                    "activated.timestamp": Variant("s", "2019-06-17T13:45:25Z"),
                    "size": Variant("i", 655414272),
                },
            ),
            (
                "bootloader.0",
                {
                    "device": Variant("s", "/dev/mmcblk2"),
                    "state": Variant("s", "inactive"),
                    "type": Variant("s", "boot-emmc"),
                    "class": Variant("s", "bootloader"),
                    "description": Variant("s", ""),
                },
            ),
            (
                "rootfs.1",
                {
                    "status": Variant("s", "ok"),
                    "bootname": Variant("s", "B"),
                    "bundle.build": Variant("s", "20190613111424"),
                    "bundle.version": Variant("s", "1.0"),
                    "bundle.compatible": Variant("s", "prusa64-sl1--prusa"),
                    "activated.count": Variant("i", 9),
                    "description": Variant("s", ""),
                    "installed.timestamp": Variant("s", "2019-06-17T13:42:03Z"),
                    "class": Variant("s", "rootfs"),
                    "boot-status": Variant("s", "good"),
                    "state": Variant("s", "inactive"),
                    "bundle.description": Variant("s", "sla-update-bundle version 1.0-r0"),
                    "installed.count": Variant("i", 8),
                    "device": Variant("s", "/dev/mmcblk2p3"),
                    "sha256": Variant("s", "1b7ad103c7f1216f351b93cd384ce5444288e6adb53ed40b81bd987b591fcbd1"),
                    "type": Variant("s", "ext4"),
                    "activated.timestamp": Variant("s", "2019-06-17T13:42:07Z"),
                    "size": Variant("i", 655414272),
                },
            ),
        ]

    @auto_dbus
    def Install(self, path: str):
        pass
