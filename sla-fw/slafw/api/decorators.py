# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2020 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2021-2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import functools
import logging
from enum import Enum
from time import monotonic
from typing import Union, List, Any, Dict, get_type_hints

from gi.repository import GLib
from pydbus import Variant
from pydbus.generic import signal

import numpy
from slafw.configs.unit import Nm, Ustep, Ms
from slafw.errors.errors import NotAvailableInState, DBusMappingException


class DBusObjectPath(str):
    pass


def state_checked(allowed_state: Union[Enum, List[Enum]]):
    """
    Decorator restricting method call based on allowed state

    :param allowed_state: State in which the method is available, or list of such states
    :return: Method decorator
    """

    def decor(function):
        @functools.wraps(function)
        def func(self, *args, **kwargs):
            if isinstance(allowed_state, list):
                allowed = [state.value for state in allowed_state]
            else:
                allowed = [allowed_state.value]

            if isinstance(self.state, Enum):
                current = self.state.value
            else:
                current = self.state

            if current not in allowed:
                raise NotAvailableInState(self.state, allowed)
            return function(self, *args, **kwargs)

        return func

    return decor


def range_checked(minimum, maximum):
    """
    Force value within range

    Raises ValueError if the only method param is not in [min, max] range. In case the value is changed towards
    the range only a warning is issued. This allows the user to adjust bad value.

    :param minimum: Minimal allowed value
    :param maximum: Maximal allowed value
    :return: Decorated property
    """

    def decor(prop: property):
        assert isinstance(prop, property)
        logger = logging.getLogger(__name__)

        @functools.wraps(prop.fset)
        def fset(self, value):
            if value < minimum:
                if value < prop.fget(self):
                    raise ValueError(f"Value: {value} out of range: [{minimum}, {maximum}]")
                logger.warning("Value %s out of range: [%s, %s]", value, minimum, maximum)
            if value > maximum:
                if value > prop.fget(self):
                    raise ValueError(f"Value: {value} out of range: [{minimum}, {maximum}]")
                logger.warning("Value %s out of range: [%s, %s]", value, minimum, maximum)
            return prop.fset(self, value)

        return property(prop.fget, fset, prop.fdel, prop.__doc__)

    return decor


def cached(validity_s: float = None):
    """
    Decorator limiting calls to property by using a cache with defined validity.
    This does not support passing arguments other than self to decorated method!

    :param validity_s: Cache validity in seconds, None means valid forever
    :return: Method decorator
    """

    def decor(function):
        cache = {}

        @functools.wraps(function)
        def func(self):
            if (
                "value" not in cache
                or "last" not in cache
                or (validity_s is not None and monotonic() - cache["last"] > validity_s)
            ):
                cache["value"] = function(self)
                cache["last"] = monotonic()
            return cache["value"]

        return func

    return decor


def dbus_api(cls):
    records: List[str] = []
    for var in vars(cls):
        obj = getattr(cls, var)
        if isinstance(obj, property):
            obj = obj.fget
        if hasattr(obj, "__dbus__"):
            record = obj.__dbus__
            assert isinstance(record, str)
            records.append(record)
    cls.dbus = f"<node><interface name='{cls.__INTERFACE__}'>{''.join(records)}</interface></node>"
    return cls


def manual_dbus(dbus: str):
    def decor(func):
        if func.__doc__ is None:
            func.__doc__ = ""
        func.__doc__ += "\n\nD-Bus interface:: \n\n\t" + "\n\t".join(dbus.splitlines())
        if isinstance(func, property):
            func.fget.__dbus__ = dbus
        else:
            func.__dbus__ = dbus
        return func

    return decor


def auto_dbus(func):
    try:
        if isinstance(func, property):
            name = func.fget.__name__
        else:
            name = func.__name__
    except Exception as e:
        raise DBusMappingException(f"Failed to obtain name for {func}") from e

    dbus = gen_method_dbus_spec(func, name)
    return manual_dbus(dbus)(func)


def auto_dbus_signal(func):
    sig = signal()
    args = gen_method_dbus_args_spec(func, signal_spec=True)
    sig.__dbus__ = f"<signal name=\"{func.__name__}\">{''.join(args)}</signal>"
    return sig


PYTHON_TO_DBUS_TYPE = {
    int: "i",
    float: "d",
    bool: "b",
    str: "s",
    numpy.float64: "d",
    Nm: "i",
    Ms: "i",
    Ustep: "i",
    DBusObjectPath: "o",
    Any: "v",
}


def python_to_dbus_type(python_type: Any) -> str:
    # TODO: Use typing.get_args and typing.get_origin once we adopt python 3.8
    if python_type in PYTHON_TO_DBUS_TYPE:
        return PYTHON_TO_DBUS_TYPE[python_type]

    if hasattr(python_type, "__origin__"):
        if python_type.__origin__ is dict:
            key = python_to_dbus_type(python_type.__args__[0])
            val = python_to_dbus_type(python_type.__args__[1])
            return "a{" + key + val + "}"

        if python_type.__origin__ is list:
            return "a" + python_to_dbus_type(python_type.__args__[0])

        if python_type.__origin__ is tuple:
            items = [python_to_dbus_type(arg) for arg in python_type.__args__]
            return "(" + "".join(items) + ")"

    raise ValueError(f"Type: {python_type} has no defined mapping to dbus")


def gen_method_dbus_spec(obj: Any, name: str) -> str:
    try:
        if isinstance(obj, property):
            access = "read"
            get_type = python_to_dbus_type(get_type_hints(obj.fget)["return"])
            if obj.fset:
                access = "readwrite"
            return f'<property name="{name}" type="{get_type}" access="{access}"></property>'
        if callable(obj):
            args = gen_method_dbus_args_spec(obj)
            return f"<method name='{name}'>{''.join(args)}</method>"
        raise ValueError(f"Unsupported dbus mapping type: {type(obj)}")
    except Exception as exception:
        raise DBusMappingException(f"Failed to generate dbus specification for {name}") from exception


def gen_method_dbus_args_spec(obj, signal_spec=False) -> List[str]:
    args = []
    for n, t in get_type_hints(obj).items():
        if t == type(None):  # TODO: Use types.NoneType in Python 3.10
            continue
        return_arg = n != "return" if signal_spec else n == "return"
        direction = "out" if return_arg else "in"
        args.append(f"<arg type='{python_to_dbus_type(t)}' name='{n}' direction='{direction}'/>")
    return args


def python_to_dbus_value_type(data: Any):
    # pylint: disable = unidiomatic-typecheck

    if isinstance(data, int):
        if data > GLib.MAXINT32 or data < GLib.MININT32:  # type: ignore[operator]
            return "x"

    if type(data) in PYTHON_TO_DBUS_TYPE:
        return PYTHON_TO_DBUS_TYPE[type(data)]

    if isinstance(data, (tuple, frozenset)):
        items = [python_to_dbus_value_type(item) for item in data]
        return "(" + "".join(items) + ")"

    if isinstance(data, list):
        dbus_type = "v"
        try:
            if data:
                childType = python_to_dbus_value_type(data[0])
                allEqual = True
                for child in data:
                    allEqual = allEqual and (childType == python_to_dbus_value_type(child))
                if allEqual:
                    dbus_type = childType
        except Exception:
            pass
        return f"a{dbus_type}"

    raise DBusMappingException(f"Failed to get value {data} dbus type")


def wrap_value(data: Any) -> Variant:
    # pylint: disable = unidiomatic-typecheck
    # pylint: disable = too-many-return-statements

    if isinstance(data, int):
        if data > GLib.MAXINT32 or data < GLib.MININT32:  # type: ignore[operator]
            return Variant("x", data)

    if type(data) in PYTHON_TO_DBUS_TYPE:
        return Variant(PYTHON_TO_DBUS_TYPE[type(data)], data)

    if isinstance(data, dict):
        return wrap_dict_value(data)

    if isinstance(data, (tuple, frozenset)):
        return Variant(python_to_dbus_value_type(data), data)

    if isinstance(data, list):
        dbus_type = python_to_dbus_value_type(data)
        if dbus_type[1] == "v":
            dbus_value = Variant(dbus_type, [wrap_value(d) for d in data])
        else:
            dbus_value = Variant(dbus_type, data)
        return dbus_value

    if isinstance(data, Enum):
        return wrap_value(data.value)

    if data is None:
        return wrap_value("None")

    raise DBusMappingException(f"Failed to wrap dbus value \"{data}\" of type {type(data)}")


def wrap_dict_value(data):
    if data:
        first_key, _ = list(data.items())[0]
        if isinstance(first_key, int):
            signature = "a{iv}"
        else:
            signature = "a{sv}"
    else:
        signature = "a{iv}"

    return Variant(signature, {key: wrap_value(val) for key, val in data.items()})


def wrap_dict_data(data: Dict[str, Any]):
    if isinstance(data, dict):
        return {key: wrap_value(val) for key, val in data.items()}
    return wrap_value(data)


def wrap_dict_data_recursive(data: Dict[str, Any]):
    if isinstance(data, dict):
        return {key: wrap_dict_data(val) for key, val in data.items()}
    return wrap_value(data)


LAST_EXCEPTION_ATTR = "_last_exception"


def last_error(method):
    @functools.wraps(method)
    def wrap(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except Exception as e:
            assert hasattr(self, LAST_EXCEPTION_ATTR)
            setattr(self, LAST_EXCEPTION_ATTR, e)
            raise e

    return wrap
