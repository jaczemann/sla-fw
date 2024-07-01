# This file is part of the SLA firmware
# Copyright (C) 2020-2021 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import re
from typing import List, Tuple, Optional, Set

import pydbus
from pydbus.generic import signal
from pydbus.registration import ObjectRegistration

from slafw.admin.items import AdminAction, AdminIntValue, AdminFloatValue, AdminBoolValue, AdminTextValue, AdminItem, \
    AdminFixedValue, AdminSelectionValue
from slafw.admin.manager import AdminManager
from slafw.admin.menu import AdminMenu
from slafw.admin.menus.root import RootMenu
from slafw.api.decorators import DBusObjectPath, dbus_api, auto_dbus, auto_dbus_signal
from slafw.errors.errors import NotAvailableInState, AdminNotAvailable
from slafw.libPrinter import Printer
from slafw.states.printer import PrinterState


@dbus_api
class Admin0ActionItem:
    """
    SL1 administrative interface action item
    """

    __INTERFACE__ = "cz.prusa3d.sl1.admin0.action"
    PropertiesChanged = signal()

    def __init__(self, item: AdminAction):
        self._item = item
        item.changed.connect(self._enabled_changed)

    @auto_dbus
    @property
    def name(self) -> str:
        return self._item.name

    @auto_dbus
    @property
    def icon(self) -> str:
        return self._item.icon

    @auto_dbus
    @property
    def enabled(self) -> bool:
        return self._item.enabled

    @auto_dbus
    def execute(self):
        print(f"Running action: {self.name}")
        self._item.execute()

    def _enabled_changed(self):
        self.PropertiesChanged(self.__INTERFACE__, {"enabled": self.enabled}, [])


@dbus_api
class Admin0IntValueItem:
    """
    SL1 administrative interface value item
    """

    __INTERFACE__ = "cz.prusa3d.sl1.admin0.value.int"
    PropertiesChanged = signal()

    def __init__(self, item: AdminIntValue):
        self._item = item
        item.changed.connect(self._value_changed)
        item.changed.connect(self._enabled_changed)

    @auto_dbus
    @property
    def name(self) -> str:
        return self._item.name

    @auto_dbus
    @property
    def icon(self) -> str:
        return self._item.icon

    @auto_dbus
    @property
    def enabled(self) -> bool:
        return self._item.enabled

    @auto_dbus
    @property
    def value(self) -> int:
        return self._item.get_value()

    @auto_dbus
    @value.setter
    def value(self, value: int):
        self._item.set_value(value)

    @auto_dbus
    @property
    def step(self) -> int:
        return self._item.step

    @auto_dbus
    @property
    def minimum(self) -> int:
        return self._item.minimum

    @auto_dbus
    @property
    def maximum(self) -> int:
        return self._item.maximum

    def _value_changed(self):
        self.PropertiesChanged(self.__INTERFACE__, {"value": self.value}, [])

    def _enabled_changed(self):
        self.PropertiesChanged(self.__INTERFACE__, {"enabled": self.enabled}, [])


@dbus_api
class Admin0FixedValueItem:
    """
    SL1 administrative interface value item
    """

    __INTERFACE__ = "cz.prusa3d.sl1.admin0.value.fixed"
    PropertiesChanged = signal()

    def __init__(self, item: AdminFixedValue):
        self._item = item
        item.changed.connect(self._value_changed)
        item.changed.connect(self._enabled_changed)

    @auto_dbus
    @property
    def name(self) -> str:
        return self._item.name

    @auto_dbus
    @property
    def icon(self) -> str:
        return self._item.icon

    @auto_dbus
    @property
    def enabled(self) -> bool:
        return self._item.enabled

    @auto_dbus
    @property
    def value(self) -> int:
        return self._item.get_value()

    @auto_dbus
    @value.setter
    def value(self, value: int):
        self._item.set_value(value)

    @auto_dbus
    @property
    def step(self) -> int:
        return self._item.step

    @auto_dbus
    @property
    def fractions(self) -> int:
        return self._item.fractions

    @auto_dbus
    @property
    def decimal_places(self) -> int:
        return self._item.decimal_places

    @auto_dbus
    @property
    def minimum(self) -> int:
        return self._item.minimum

    @auto_dbus
    @property
    def maximum(self) -> int:
        return self._item.maximum

    def _value_changed(self):
        self.PropertiesChanged(self.__INTERFACE__, {"value": self.value}, [])

    def _enabled_changed(self):
        self.PropertiesChanged(self.__INTERFACE__, {"enabled": self.enabled}, [])


@dbus_api
class Admin0FloatValueItem:
    """
    SL1 administrative interface value item
    """

    __INTERFACE__ = "cz.prusa3d.sl1.admin0.value.float"
    PropertiesChanged = signal()

    def __init__(self, item: AdminFloatValue):
        self._item = item
        item.changed.connect(self._value_changed)
        item.changed.connect(self._enabled_changed)

    @auto_dbus
    @property
    def name(self) -> str:
        return self._item.name

    @auto_dbus
    @property
    def icon(self) -> str:
        return self._item.icon

    @auto_dbus
    @property
    def enabled(self) -> bool:
        return self._item.enabled

    @auto_dbus
    @property
    def value(self) -> float:
        return self._item.get_value()

    @auto_dbus
    @value.setter
    def value(self, value: float):
        self._item.set_value(value)

    @auto_dbus
    @property
    def step(self) -> float:
        return self._item.step

    @auto_dbus
    @property
    def minimum(self) -> int:
        return self._item.minimum

    @auto_dbus
    @property
    def maximum(self) -> int:
        return self._item.maximum

    def _value_changed(self):
        self.PropertiesChanged(self.__INTERFACE__, {"value": self.value}, [])

    def _enabled_changed(self):
        self.PropertiesChanged(self.__INTERFACE__, {"enabled": self.enabled}, [])


@dbus_api
class Admin0SelectionItem:
    """
    SL1 administrative interface value item
    """

    __INTERFACE__ = "cz.prusa3d.sl1.admin0.value.selection"
    PropertiesChanged = signal()

    def __init__(self, item: AdminSelectionValue):
        self._item = item
        item.changed.connect(self._value_changed)
        item.changed.connect(self._enabled_changed)

    @auto_dbus
    @property
    def name(self) -> str:
        return self._item.name

    @auto_dbus
    @property
    def icon(self) -> str:
        return self._item.icon

    @auto_dbus
    @property
    def enabled(self) -> bool:
        return self._item.enabled

    @auto_dbus
    @property
    def value(self) -> int:
        return self._item.get_value()

    @auto_dbus
    @value.setter
    def value(self, value: int):
        self._item.set_value(value)

    @auto_dbus
    @property
    def selection(self) -> List[str]:
        return self._item.selection

    @auto_dbus
    @property
    def wrap_around(self) -> bool:
        return self._item.wrap_around

    def _value_changed(self):
        self.PropertiesChanged(self.__INTERFACE__, {"value": self.value}, [])

    def _enabled_changed(self):
        self.PropertiesChanged(self.__INTERFACE__, {"enabled": self.enabled}, [])


@dbus_api
class Admin0BoolValueItem:
    """
    SL1 administrative interface value item
    """

    __INTERFACE__ = "cz.prusa3d.sl1.admin0.value.bool"
    PropertiesChanged = signal()

    def __init__(self, item: AdminBoolValue):
        self._item = item
        item.changed.connect(self._value_changed)
        item.changed.connect(self._enabled_changed)

    @auto_dbus
    @property
    def name(self) -> str:
        return self._item.name

    @auto_dbus
    @property
    def icon(self) -> str:
        return self._item.icon

    @auto_dbus
    @property
    def enabled(self) -> bool:
        return self._item.enabled

    @auto_dbus
    @property
    def value(self) -> bool:
        return self._item.get_value()

    @auto_dbus
    @value.setter
    def value(self, value: bool):
        self._item.set_value(value)

    def _value_changed(self):
        self.PropertiesChanged(self.__INTERFACE__, {"value": self.value}, [])

    def _enabled_changed(self):
        self.PropertiesChanged(self.__INTERFACE__, {"enabled": self.enabled}, [])


@dbus_api
class Admin0TextValueItem:
    """
    SL1 administrative interface value item
    """

    __INTERFACE__ = "cz.prusa3d.sl1.admin0.value.text"
    PropertiesChanged = signal()

    def __init__(self, item: AdminTextValue):
        self._item = item
        item.changed.connect(self._value_changed)
        item.changed.connect(self._enabled_changed)

    @auto_dbus
    @property
    def name(self) -> str:
        return self._item.name

    @auto_dbus
    @property
    def icon(self) -> str:
        return self._item.icon

    @auto_dbus
    @property
    def enabled(self) -> bool:
        return self._item.enabled

    @auto_dbus
    @property
    def value(self) -> str:
        return self._item.get_value()

    @auto_dbus
    @value.setter
    def value(self, value: str):
        self._item.set_value(value)

    def _value_changed(self):
        self.PropertiesChanged(self.__INTERFACE__, {"value": self.value}, [])

    def _enabled_changed(self):
        self.PropertiesChanged(self.__INTERFACE__, {"enabled": self.enabled}, [])


@dbus_api
class Admin0:
    """
    SL1 administrative DBus interface

    This provides backed managed access to generic printer functions used for maintenance and testing. Do not use this
    in production. Dragons ahead !!!
    """

    __INTERFACE__ = "cz.prusa3d.sl1.admin0"
    ALLOWED_ENTER_STATES = [PrinterState.RUNNING, PrinterState.PRINTING, PrinterState.ADMIN]

    DBUS_NAME_REPLACE_PATTERN = re.compile(r"[^A-Za-z0-9_]")

    PropertiesChanged = signal()

    @auto_dbus_signal
    def enter_sysinfo(self):
        pass

    @auto_dbus_signal
    def enter_touchscreen_test(self):
        pass

    @auto_dbus_signal
    def enter_fullscreen_image(self):
        pass

    @auto_dbus_signal
    def enter_tower_moves(self):
        pass

    @auto_dbus_signal
    def enter_tilt_moves(self):
        pass

    def __init__(self, manager: AdminManager, printer: Printer):
        self._logger = logging.getLogger(__name__)
        self._manager = manager
        self._printer = printer
        self._item_registrations: Set[ObjectRegistration] = set()
        self._item_names: Set[AdminItem, str] = set()
        self._children: List[Tuple[str, DBusObjectPath]] = []
        self._bus_name = None
        manager.menu_changed.connect(self._on_menu_change)
        manager.enter_sysinfo.connect(self._on_enter_sysinfo)
        manager.enter_touchscreen_test.connect(self._on_enter_touchscreen_test)
        manager.enter_fullscreen_image.connect(self._on_enter_fullscreen_image)
        manager.enter_tower_moves.connect(self._on_enter_tower_moves)
        manager.enter_tilt_moves.connect(self._on_enter_tilt_moves)

    def _on_enter_sysinfo(self):
        self.enter_sysinfo()

    def _on_enter_touchscreen_test(self):
        self.enter_touchscreen_test()

    def _on_enter_fullscreen_image(self):
        self.enter_fullscreen_image()

    def _on_enter_tower_moves(self):
        self.enter_tower_moves()

    def _on_enter_tilt_moves(self):
        self.enter_tilt_moves()

    @auto_dbus
    def enter(self) -> None:
        if self._printer.state not in self.ALLOWED_ENTER_STATES:
            raise NotAvailableInState(self._printer.state, self.ALLOWED_ENTER_STATES)
        if not self._printer.runtime_config.show_admin:
            raise AdminNotAvailable()
        self._manager.enter(RootMenu(self._manager, self._printer))

    @auto_dbus
    @property
    def children(self) -> List[Tuple[str, DBusObjectPath]]:
        return self._children

    @property
    def _current_menu(self) -> Optional[AdminMenu]:
        return self._manager.current_menu

    def _on_menu_change(self):
        if self._current_menu:
            self._current_menu.items_changed.connect(self._on_menu_change)

        self._update_items()
        self.PropertiesChanged(self.__INTERFACE__, {"children": self.children}, [])
        self._printer.set_state(PrinterState.ADMIN, bool(self.children))

    def _update_items(self):
        bus = pydbus.SystemBus()

        self._logger.debug("Unregistering items")
        while self._item_registrations:
            self._item_registrations.pop().unregister()

        self._item_names = set()
        self._children.clear()

        self._logger.debug("Registering new items")
        if not self._current_menu:
            self._logger.debug("No menu -> no items")
            return

        for item in self._current_menu.items.values():
            dbus_name = self.DBUS_NAME_REPLACE_PATTERN.sub("_", item.name)
            if len(dbus_name) < 2:
                dbus_name += "__"

            if isinstance(item, AdminAction):
                self._item_registrations.add(
                    bus.register_object(f"/cz/prusa3d/sl1/admin0/Items/{dbus_name}", Admin0ActionItem(item), None)
                )
                self._item_names.add((Admin0ActionItem.__INTERFACE__, dbus_name))
                self._children.append(
                    (Admin0ActionItem.__INTERFACE__, DBusObjectPath(f"/cz/prusa3d/sl1/admin0/Items/{dbus_name}"))
                )
            elif isinstance(item, AdminIntValue):
                self._item_registrations.add(
                    bus.register_object(f"/cz/prusa3d/sl1/admin0/Items/{dbus_name}", Admin0IntValueItem(item), None)
                )
                self._item_names.add((Admin0IntValueItem.__INTERFACE__, dbus_name))
                self._children.append(
                    (Admin0IntValueItem.__INTERFACE__, DBusObjectPath(f"/cz/prusa3d/sl1/admin0/Items/{dbus_name}"))
                )
            elif isinstance(item, AdminFixedValue):
                self._item_registrations.add(
                    bus.register_object(f"/cz/prusa3d/sl1/admin0/Items/{dbus_name}", Admin0FixedValueItem(item), None)
                )
                self._item_names.add((Admin0FixedValueItem.__INTERFACE__, dbus_name))
                self._children.append(
                    (Admin0FixedValueItem.__INTERFACE__, DBusObjectPath(f"/cz/prusa3d/sl1/admin0/Items/{dbus_name}"))
                )
            elif isinstance(item, AdminFloatValue):
                self._item_registrations.add(
                    bus.register_object(f"/cz/prusa3d/sl1/admin0/Items/{dbus_name}", Admin0FloatValueItem(item), None)
                )
                self._item_names.add((Admin0FloatValueItem.__INTERFACE__, dbus_name))
                self._children.append(
                    (Admin0FloatValueItem.__INTERFACE__, DBusObjectPath(f"/cz/prusa3d/sl1/admin0/Items/{dbus_name}"))
                )
            elif isinstance(item, AdminBoolValue):
                self._item_registrations.add(
                    bus.register_object(f"/cz/prusa3d/sl1/admin0/Items/{dbus_name}", Admin0BoolValueItem(item), None)
                )
                self._item_names.add((Admin0BoolValueItem.__INTERFACE__, dbus_name))
                self._children.append(
                    (Admin0BoolValueItem.__INTERFACE__, DBusObjectPath(f"/cz/prusa3d/sl1/admin0/Items/{dbus_name}"))
                )
            elif isinstance(item, AdminTextValue):
                self._item_registrations.add(
                    bus.register_object(f"/cz/prusa3d/sl1/admin0/Items/{dbus_name}", Admin0TextValueItem(item), None)
                )
                self._item_names.add((Admin0TextValueItem.__INTERFACE__, dbus_name))
                self._children.append(
                    (Admin0TextValueItem.__INTERFACE__, DBusObjectPath(f"/cz/prusa3d/sl1/admin0/Items/{dbus_name}"))
                )
            elif isinstance(item, AdminSelectionValue):
                self._item_registrations.add(
                    bus.register_object(f"/cz/prusa3d/sl1/admin0/Items/{dbus_name}", Admin0SelectionItem(item), None)
                )
                self._item_names.add((Admin0SelectionItem.__INTERFACE__, dbus_name))
                self._children.append(
                    (Admin0SelectionItem.__INTERFACE__, DBusObjectPath(f"/cz/prusa3d/sl1/admin0/Items/{dbus_name}"))
                )
            else:
                self._logger.warning("Item name: %s has no mapping, ignoring", item.name)
                continue
