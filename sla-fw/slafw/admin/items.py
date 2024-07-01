# This file is part of the SLA firmware
# Copyright (C) 2020-2021 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

# pylint: disable = too-many-arguments

from __future__ import annotations

from functools import partial, wraps
from typing import Callable, Any, Optional, List
from PySignal import Signal

from slafw.configs.unit import Unit, Nm, Ms


class AdminItem:
    # pylint: disable=too-few-public-methods
    def __init__(
            self,
            name: str,
            icon: str="",
            enabled: bool=True):
        self.name = name
        self.icon = icon
        self._enabled = enabled
        self.changed = Signal()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, enabled: bool):
        self._enabled = enabled
        self.changed.emit()


class AdminAction(AdminItem):
    # pylint: disable=too-few-public-methods
    def __init__(
            self,
            name: str,
            action: Callable,
            icon: str="",
            enabled: bool=True):
        super().__init__(name, icon, enabled)
        self._action = action

    def execute(self):
        self._action()


class AdminValue(AdminItem):
    def __init__(
            self,
            name: str,
            getter: Callable,
            setter: Callable,
            icon: str="",
            enabled: bool=True):
        super().__init__(name, icon, enabled)
        self._getter = getter
        self._setter = setter

    def get_value(self) -> Any:
        return self._getter()

    def set_value(self, value: Any) -> None:
        self._setter(value)
        self.changed.emit()

    def wrap_setter(self, setter: Callable[[Any], None]):
        if not setter:
            return setter

        @wraps(setter)
        def wrap(*args, **kwargs):
            ret = setter(*args, **kwargs)
            self.changed.emit()
            return ret

        return wrap

    @classmethod
    def _get_prop_name(cls, obj: object, prop: property):
        for name in dir(type(obj)):
            if getattr(type(obj), name) == prop:
                return name
        raise ValueError("Failed to map value to property")

    @classmethod
    def _map_prop(cls, obj: object, prop: property, value: AdminValue, prop_name: str):
        new_prop = property(prop.fget, value.wrap_setter(prop.fset), prop.fdel, prop.__doc__)
        setattr(type(obj), prop_name, new_prop)


class AdminMinMaxValue(AdminValue):
    def __init__(
            self,
            name: str,
            getter: Callable,
            setter: Callable,
            icon: str="",
            enabled: bool=True,
            minimum: int=None,
            maximum: int=None):
        super().__init__(name, getter, setter, icon, enabled)
        self._minimum = -0x7fffffff if minimum is None else minimum
        self._maximum = 0x7fffffff if maximum is None else maximum

    @property
    def minimum(self) -> int:
        return self._minimum

    @property
    def maximum(self) -> int:
        return self._maximum

    @staticmethod
    def _get_params_from_value(obj: object, prop: str):
        valget = getattr(obj, "get_value_property", None)
        if callable(valget):
            return valget(prop, "unit"), valget(prop, "min"), valget(prop, "max")
        return None, None, None


class AdminIntValue(AdminMinMaxValue):
    def __init__(
            self,
            name: str,
            getter: Callable,
            setter: Callable,
            step: int,
            icon: str="",
            enabled: bool=True,
            minimum: int=None,
            maximum: int=None):
        super().__init__(name, getter, setter, icon, enabled, minimum, maximum)
        self._step = step

    @classmethod
    def from_value(
            cls,
            name: str,
            obj: object,
            prop: str,
            step: int,
            icon: str="",
            enabled: bool=True) -> AdminIntValue:
        unit, minimum, maximum = cls._get_params_from_value(obj, prop)

        def g():
            return getattr(obj, prop)

        def s(value):
            if callable(unit):
                value = unit(value)
            setattr(obj, prop, value)

        return AdminIntValue(name, g, s, step, icon, enabled, minimum, maximum)

    @classmethod
    def from_property(
            cls,
            obj: object,
            prop: property,
            step: int,
            icon: str="",
            enabled: bool=True,
            minimum: int=None,
            maximum: int=None) -> AdminIntValue:
        prop_name = cls._get_prop_name(obj, prop)
        value = AdminIntValue(
                prop_name,
                partial(prop.fget, obj),
                partial(prop.fset, obj),
                step,
                icon,
                enabled,
                minimum,
                maximum)
        cls._map_prop(obj, prop, value, prop_name)
        return value

    @property
    def step(self) -> int:
        return self._step


class AdminFixedValue(AdminMinMaxValue):
    def __init__(
            self,
            name: str,
            getter: Callable,
            setter: Callable,
            unit: Optional[Unit]=None,
            step: int=None,
            fractions: int=None,
            decimal_places: int=None,
            icon: str="",
            enabled: bool=True,
            minimum: int=None,
            maximum: int=None):
        super().__init__(name, getter, setter, icon, enabled, minimum, maximum)
        if step is None:
            if issubclass(unit, Nm):
                step = 10000
            elif issubclass(unit, Ms):
                step = 100
            else:
                step = 1
        if fractions is None:
            if issubclass(unit, Nm):
                fractions = 6
            elif issubclass(unit, Ms):
                fractions = 3
            else:
                fractions = 0
        if decimal_places is None:
            if issubclass(unit, Nm):
                decimal_places = 2
            elif issubclass(unit, Ms):
                decimal_places = 1
            else:
                decimal_places = 0
        self._step = step
        self._fractions = fractions
        self._decimal_places = decimal_places

    @classmethod
    def from_value(
            cls,
            name: str,
            obj: object,
            prop: str,
            step: int=None,
            fractions: int=None,
            decimal_places: int=None,
            icon: str="",
            enabled: bool=True) -> AdminFixedValue:
        unit, minimum, maximum = cls._get_params_from_value(obj, prop)

        def g():
            return getattr(obj, prop)

        def s(value):
            if callable(unit):
                value = unit(value)
            setattr(obj, prop, value)

        return AdminFixedValue(name, g, s, unit, step, fractions, decimal_places, icon, enabled, minimum, maximum)

    @classmethod
    def from_property(
            cls,
            obj: object,
            prop: property,
            step: int=None,
            fractions: int=None,
            decimal_places: int=None,
            icon: str="",
            enabled: bool=True) -> AdminFixedValue:
        prop_name = cls._get_prop_name(obj, prop)
        unit, minimum, maximum = cls._get_params_from_value(obj, prop)
        value = AdminFixedValue(
                prop_name,
                partial(prop.fget, obj),
                partial(prop.fset, obj),
                unit,
                step,
                fractions,
                decimal_places,
                icon,
                enabled,
                minimum,
                maximum)
        cls._map_prop(obj, prop, value, prop_name)
        return value

    @property
    def step(self) -> int:
        return self._step

    @property
    def fractions(self) -> int:
        return self._fractions

    @property
    def decimal_places(self) -> int:
        return self._decimal_places


class AdminFloatValue(AdminMinMaxValue):
    def __init__(
            self,
            name: str,
            getter: Callable,
            setter: Callable,
            step: float,
            icon: str="",
            enabled: bool=True,
            minimum: int=None,
            maximum: int=None):
        super().__init__(name, getter, setter, icon, enabled, minimum, maximum)
        self._step = step

    @classmethod
    def from_value(
            cls,
            name: str,
            obj: object,
            prop: str,
            step: float,
            icon: str="",
            enabled: bool=True) -> AdminFloatValue:
        _, minimum, maximum = cls._get_params_from_value(obj, prop)

        def g():
            return getattr(obj, prop)

        def s(value):
            setattr(obj, prop, value)

        return AdminFloatValue(name, g, s, step, icon, enabled, minimum, maximum)

    @classmethod
    def from_property(
            cls,
            obj: object,
            prop: property,
            step: float,
            icon: str="",
            enabled: bool=True,
            minimum: int=None,
            maximum: int=None) -> AdminFloatValue:
        prop_name = cls._get_prop_name(obj, prop)
        value = AdminFloatValue(
                prop_name,
                partial(prop.fget, obj),
                partial(prop.fset, obj),
                step,
                icon,
                enabled,
                minimum,
                maximum)
        cls._map_prop(obj, prop, value, prop_name)
        return value

    @property
    def step(self) -> float:
        return self._step


class AdminBoolValue(AdminValue):
    @classmethod
    def from_value(
            cls,
            name: str,
            obj: object,
            prop: str,
            icon: str="",
            enabled: bool=True) -> AdminBoolValue:
        return AdminBoolValue(
                name,
                partial(getattr, obj, prop),
                partial(setattr, obj, prop),
                icon,
                enabled)

    @classmethod
    def from_property(
            cls,
            obj: object,
            prop: property,
            icon: str="",
            enabled: bool=True) -> AdminBoolValue:
        prop_name = cls._get_prop_name(obj, prop)
        value = AdminBoolValue(
                prop_name,
                partial(prop.fget, obj),
                partial(prop.fset, obj),
                icon,
                enabled)
        cls._map_prop(obj, prop, value, prop_name)
        return value


class AdminTextValue(AdminValue):
    @classmethod
    def from_value(
            cls,
            name: str,
            obj: object,
            prop: str,
            icon: str="",
            enabled: bool=True):
        return AdminTextValue(
                name,
                partial(getattr, obj, prop),
                partial(setattr, obj, prop),
                icon,
                enabled)

    @classmethod
    def from_property(
            cls,
            obj: object,
            prop: property,
            icon: str="",
            enabled: bool=True):
        prop_name = cls._get_prop_name(obj, prop)
        value = AdminTextValue(
                prop_name,
                partial(prop.fget, obj),
                partial(prop.fset, obj),
                icon,
                enabled)
        cls._map_prop(obj, prop, value, prop_name)
        return value


class AdminLabel(AdminTextValue):
    INSTANCE_COUNTER = 0

    def __init__(
            self,
            initial_text: Optional[str]=None,
            icon: str="",
            enabled: bool=True):
        super().__init__(
                f"Admin label {AdminLabel.INSTANCE_COUNTER}",
                self.label_get_value,
                self.set,
                icon,
                enabled)
        AdminLabel.INSTANCE_COUNTER += 1
        self._label_value = initial_text if initial_text is not None else self.name

    def label_get_value(self) -> str:
        return self._label_value

    def set(self, value: str):
        self._label_value = value
        self.changed.emit()


class AdminSelectionValue(AdminValue):
    """Allow selection of an item from a preset list, value is an index in the list"""
    def __init__(
            self,
            name: str,
            getter: Callable,
            setter: Callable,
            selection: List[str],
            wrap_around: bool=False,
            icon: str="",
            enabled: bool=True):
        super().__init__(name, getter, setter, icon, enabled)
        self._selection = selection
        self._wrap_around = wrap_around

    @classmethod
    def from_value(
            cls,
            name: str,
            obj: object,
            prop: str,
            selection: List[str],
            wrap_around: bool=False,
            icon: str="",
            enabled: bool=True) -> AdminSelectionValue:
        def g():
            return getattr(obj, prop)

        def s(value):
            setattr(obj, prop, value)

        return AdminSelectionValue(name, g, s, selection, wrap_around, icon, enabled)

    @classmethod
    def from_property(
            cls,
            obj: object,
            prop: property,
            selection: List[str],
            wrap_around: bool=False,
            icon: str="",
            enabled: bool=True) -> AdminSelectionValue:
        prop_name = cls._get_prop_name(obj, prop)
        value = AdminSelectionValue(
                prop_name,
                partial(prop.fget, obj),
                partial(prop.fset, obj),
                selection,
                wrap_around,
                icon,
                enabled)
        cls._map_prop(obj, prop, value, prop_name)
        return value

    @property
    def selection(self) -> List[str]:
        return self._selection

    @property
    def wrap_around(self) -> bool:
        return self._wrap_around
