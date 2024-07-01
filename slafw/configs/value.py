# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2020-2024 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

# TODO: Fix following pylint problems
# pylint: disable=too-many-arguments

import functools
import logging
import re
import weakref
from abc import abstractmethod, ABC
from pathlib import Path
from typing import Optional, List, Dict, Type, Union, Any, Callable, Set
from queue import Queue
from readerwriterlock import rwlock

from slafw.configs.unit import Unit
from slafw.errors.errors import ConfigException
from slafw import test_runtime


class BaseConfig(ABC):
    # pylint: disable=too-many-instance-attributes

    """
    Base class of the configuration

    This contains bare minimum for use by Value class
    """

    @abstractmethod
    def __init__(self, is_master: bool = False):
        self._lower_to_normal_map: Dict[str, str] = {}
        self._logger = logging.getLogger("slafw.configs")   # FIXME __name__ or "slafw.configs.value" does not log
        self._is_master = is_master
        self._lock = rwlock.RWLockRead()
        self._data_values: Dict[str, Any] = {}
        self._data_raw_values: Dict[str, Any] = {}
        self._data_factory_values: Dict[str, Any] = {}
        self._data_default_values: Dict[str, Any] = {}

    @property
    def lock(self) -> rwlock.RWLockRead:
        return self._lock

    @property
    def data_values(self) -> Dict[str, Any]:
        return self._data_values

    @property
    def data_raw_values(self) -> Dict[str, Any]:
        return self._data_raw_values

    @property
    def data_factory_values(self) -> Dict[str, Any]:
        return self._data_factory_values

    @property
    def data_default_values(self) -> Dict[str, Any]:
        return self._data_default_values

    def lower_to_normal_map(self, key: str) -> Optional[str]:
        """
        Map key from low-case to the standard (as defined) case

        :param key: Input lowcase name
        :return: Standard key name or None if not found
        """
        return self._lower_to_normal_map.get(key)

    def is_master(self):
        return self._is_master


class Value(property, ABC):
    # pylint: disable=too-many-instance-attributes
    """
    Base class for values included in configuration files.

    This class does most of the configuration magic. It inherits from property, so that ints instances can be
    set and read as properties. Also it holds data describing the configuration key such as name, key, type, default...
    The current value and factory value are provided as properties as these values needs to be stored in the
    configuration object. Keep in mind that the property is instantiated at class definition time. Multiple instances of
    the same configuration class share the value instances.

    Apart from data the Value class also implements necessary methods for the property access and implements basic
    value get/set logic including type checking and default/factory value reading. Additional check can be implemented
    by classes inheriting from Value by override of adapt and check methods.
    """

    @abstractmethod
    def __init__(self, value_type: List[Type], default=None, key=None, factory=False, doc="", unit: type=None):
        """
        Config value constructor

        :param value_type: List of types this value can be instance of. (used to specify [int, float], think twice
         before passing multiple values)
        :param default: Default value. Can be function that receives configuration instance as the only parameter and
         returns default value.
        :param key: Key name in the configuration file. If set to None (default) it will be set to property name.
        :param factory: Whenever the value should be stored in factory configuration file.
        :param doc: Documentation string from the configuration item
        :param unit: unit of given value such as Ustep or Nm. Dbus currently does not support custom data types.
         So values including unit must be saved with the unit manually.
        """

        def getter(config: BaseConfig) -> value_type[0]:  # type: ignore
            with config.lock.gen_rlock():
                return self.value_getter(config)

        def setter(config: BaseConfig, val: value_type[0]):  # type: ignore
            # TODO: Take a write lock once we get rid of writable properties
            # with self.config.lock.gen_wlock():
            self.value_setter(config, val)

        def deleter(config: BaseConfig):
            self.set_value(config, None)
            self.set_raw_value(config, None)

        super().__init__(getter, setter, deleter)
        self.logger = logging.getLogger(__name__)
        self.name: Optional[str] = None
        self.key = key
        self.type: List[Type] = value_type
        self.default = default
        self.factory = factory
        self.default_doc = doc
        self.unit: Optional[type] = unit

    def base_doc(self) -> str:
        """
        Get base docstring describing the value

        :return: Docstring text
        """
        if any(isinstance(self.default, t) for t in self.type):
            doc_default = str(self.default).lower()
        else:
            doc_default = "<Computed>"
        return f"""{self.default_doc}

            :type: {" ".join([t.__name__ for t in self.type])}

            :default: {str(doc_default).lower()}
            :key: {self.key}
        """

    def check(self, val) -> None:
        """
        Check value to match config file specification.

        This is called after value adaptation. This method is supposed to raise exceptions when value is not as
        requested.

        :param val: Value to check
        """
        t = self.unit if self.unit else tuple(self.type)
        if not isinstance(val, t):
            raise ValueError(f"Value \"{val}\" not compatible with \"{t}\"")

    def adapt(self, val):  # pylint: disable = no-self-use
        """
        Adapt value being set

        This method adapts value before it is checked ad stored as new configuration value. This is can be used to
        adjust the value to new minimum/maximum. Default implementation is pass-through.

        :param val: Value to adapt
        :return: Adapted value
        """
        return val

    def get_value(self, config: BaseConfig) -> Any:
        """
        Get current value stored in configuration file

        Data are read from Config instance as value instances are per config type.

        :param config: Config to read from
        :return: Value
        """
        value = config.data_values[self.name]
        if value is None or self.unit is None:
            return value
        return self.unit(value)

    def set_value(self, config: BaseConfig, value: Any) -> None:
        config.data_values[self.name] = value

    def get_raw_value(self, config: BaseConfig) -> Any:
        """
        Get current raw (unadapted) value stored in configuration file

        Data are read from Config instance as value instances are per config type.

        :param config: Config to read from
        :return: Value
        """
        value = config.data_raw_values[self.name]
        if value is None or self.unit is None:
            return value
        return self.unit(value)

    def set_raw_value(self, config: BaseConfig, value: Any) -> None:
        config.data_raw_values[self.name] = value

    def get_factory_value(self, config: BaseConfig) -> Any:
        """
        Get current factory value stored in configuration file

        Data are read from Config instance as value instances are per config type.

        :param config: Config to read from
        :return: Value
        """
        return config.data_factory_values[self.name]

    def set_factory_value(self, config: BaseConfig, value: Any) -> None:
        config.data_factory_values[self.name] = value

    def get_default_value(self, config: BaseConfig) -> Any:
        if not any(isinstance(self.default, t) for t in self.type) and callable(self.default) and config:
            return self.default(config)
        default = config.data_default_values.get(self.name, self.default)
        if default is None or self.unit is None:
            return default
        return self.unit(default)

    def set_default_value(self, config: BaseConfig, value: Any) -> None:
        config.data_default_values[self.name] = value

    def setup(self, config: BaseConfig, name: str) -> None:
        """
        Set instance of the config, this value is part of and its name

        :param config: Config this value is part of
        :param name: Name of this value in the config
        """
        self.name = name
        if self.key is None:
            self.key = name
        self.set_value(config, None)
        self.set_raw_value(config, None)
        self.set_factory_value(config, None)

    def value_setter(
        self, config: BaseConfig, val, write_override: bool = False, factory: bool = False, defaults: bool = False,
        dry_run = False
    ) -> None:
        """
        Config item value setter

        :param config: Config to read from
        :param val: New value to set (must have already correct type)
        :param write_override: Set value even when config is read-only (!is_master) Used internally while reading config
         data from file.
        :param factory: Whenever to set factory value instead of normal value. Defaults to normal value
        :param defaults: Whenever to set default value instead of normal value. Defaults to normal value
        :param dry_run: If set to true the value is not actually set. Used to check value consistency.
        """
        if test_runtime.testing:
            write_override = True
        try:
            if not config.is_master() and not write_override:
                raise ConfigException("Cannot write to read-only config !!!")
            if val is None:
                raise ValueError(f"Using default for key {self.name} as {val} is None")
            if not any(isinstance(val, t) for t in self.type):
                raise ValueError(f"Using default for key {self.name} as {val} is {type(val)} but should be {self.type}")
            adapted = self.adapt(val)
            if adapted != val:
                self.logger.warning("Adapting config value %s from %s to %s", self.name, val, adapted)
            self.check(adapted)

            if dry_run:
                return

            if defaults:
                self.set_default_value(config, val)
            elif factory:
                self.set_factory_value(config, adapted)
            else:
                self.set_value(config, adapted)
                self.set_raw_value(config, val)
        except (ValueError, ConfigException, TypeError) as exception:
            raise ConfigException(f"Setting config value {self.name} to {val} failed") from exception

    def value_getter(self, config: BaseConfig) -> Any:
        """
        Configuration value getter

        :param config: Config to read from
        :return: Config value or factory value or default value
        """
        if self.get_value(config) is not None:
            return self.get_value(config)

        if self.get_factory_value(config) is not None:
            return self.get_factory_value(config)

        return self.get_default_value(config)

    @property
    def file_key(self) -> str:
        """
        Getter for file key for the configuration item.

        :return: File key string for the configuration value
        """
        return self.key if self.key else self.name

    def is_default(self, config: BaseConfig) -> bool:
        """
        Test for value being set to default

        :param config: Config to read from
        :return: True if default, False otherwise
        """
        return (self.get_value(config) is None or self.get_value(config) == self.get_default_value(config)) and (
            self.get_factory_value(config) is None or self.get_factory_value(config) == self.get_default_value(config)
        )

    def presentation(self, val):
        # pylint: disable=no-self-use
        return val


class BoolValue(Value):
    """
    Bool configuration value class

    Just sets bool type to base Value class constructor. Bools do not require special handling.
    """

    def __init__(self, *args, **kwargs):
        super().__init__([bool], *args, **kwargs)
        self.__doc__ = self.base_doc()


class NumericValue(Value):
    """
    Numerical configuration value class

    Accepts minimum and maximum, implements value adaptation.
    """

    def __init__(self, *args, minimum: Optional = None, maximum: Optional = None, **kwargs):
        """
        Numeric config value constructor

        :param minimum: Minimal allowed value, None means no restriction
        :param maximum: Maximal allowed value, None means no restriction
        """
        super().__init__(*args, **kwargs)
        self.min = minimum
        if minimum is not None and self.unit is not None:
            self.min = self.unit(minimum)
        self.max = maximum
        if maximum is not None and self.unit is not None:
            self.max = self.unit(maximum)
        self.__doc__ = f"""{self.base_doc()}
            :range: {self.min} - {self.max}
        """

    def adapt(self, val: Optional[Union[int, float]]):
        """
        Adapt value to minimum and maximum

        :param val: Initial value
        :return: Adapted value
        """
        if self.max is not None and val > self.max:
            return self.max

        if self.min is not None and val < self.min:
            return self.min

        return val


class IntValue(NumericValue):
    """
    Integer configuration value
    """

    def __init__(self, *args, **kwargs):
        super().__init__([int, Unit], *args, **kwargs)


class FloatValue(NumericValue):
    """
    Float configuration value
    """

    def __init__(self, *args, **kwargs):
        super().__init__([float, int], *args, **kwargs)

    def adapt(self, val: Optional[Union[int, float]]):
        adapted = super().adapt(val)
        if isinstance(val, int):
            return float(adapted)
        return adapted


class ProfileIndex(NumericValue):
    """
    Integer configuration value
    """

    def __init__(self, *args, **kwargs):
        self.options = list(self._profile_names(args[0]))
        super().__init__([int], minimum=0, maximum=len(self.options)-1, **kwargs)

    @staticmethod
    def _profile_names(profile):
        for name in profile.__definition_order__:
            if not name.startswith("_"):
                yield name

    def value_setter(
        self, config: BaseConfig, val, write_override: bool = False, factory: bool = False, defaults: bool = False,
        dry_run = False
    ) -> None:
        if isinstance(val, str):
            try:
                val = self.options.index(val)
            except ValueError as e:
                raise ConfigException(f"{self.file_key} has no index for option '{val}'") from e
        super().value_setter(config, val, write_override, factory, defaults, dry_run)

    def presentation(self, val):
        return self.options[val]


class ListValue(Value):
    """
    List configuration value

    Add length to value properties.
    """

    def __init__(self, value_type: List[Type], *args, length: Optional[int] = None, **kwargs):
        """
        List configuration value constructor

        :param value_type: List of acceptable inner value types
        :param length: Required list length, None means no check
        """
        super().__init__([list], *args, **kwargs)
        self.length = length
        self.inner_type = value_type
        self.__doc__ = self.base_doc()
        self.__doc__ = f"""{self.base_doc()}
            :length: {self.length}
        """

    def check(self, val: Optional[List[int]]) -> None:
        """
        Check list value for correct internal type and number of elements

        :param val: Value to check
        """
        if any(not any(isinstance(x, t) for t in self.inner_type) for x in val):
            raise ValueError(f"Using default for key {self.name} as {val} is has incorrect inner type")
        if self.length is not None and len(val) != self.length:
            raise ValueError(f"Using default for key {self.name} as {val} does not match required length")


class IntListValue(ListValue):
    """
    Integer list configuration value
    """

    def __init__(self, *args, **kwargs):
        super().__init__([int], *args, **kwargs)


class FloatListValue(ListValue):
    """
   Float list configuration value
   """

    def __init__(self, *args, **kwargs):
        super().__init__([float, int], *args, **kwargs)

class TextValue(Value):
    """
    Text list configuration value
    """

    def __init__(self, default: Optional[str] = "", regex: str = ".*", **kwargs):
        """
        Text list configuration value constructor

        :param regex: Regular expression the string has to match.
        """
        super().__init__([str], default, **kwargs)
        self.regex = re.compile(regex)
        self.__doc__ = f"""{self.base_doc()}
            :regex: {regex}
        """

    def check(self, val: str) -> None:
        """
        Check value for regular expression match

        :param val: Value to check
        """
        if not self.regex.fullmatch(val):
            raise ValueError(f'Value {self.name} cannot be set. Value "{val}" does not match "{self.regex}"')


class DictOfConfigs(Value):
    """
    Dict configuration value

    Add recursion to value properties.
    """

    def __init__(self, value_type: Type, *args, **kwargs):
        """
        List configuration value constructor

        :param value_type: acceptable inner value type
        """
        super().__init__([value_type], *args, **kwargs)





class ValueConfig(BaseConfig):
    """
    ValueConfig is as interface implementing all the necessary stuff for ConfigWriter operations
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._on_change: Set[Callable[[str, Any], None]] = set()
        self._stored_callbacks: Queue[Callable[[], None]] = Queue()
        self._values: Dict[str, Value] = {}
        for var in dir(self.__class__):
            obj = getattr(self.__class__, var)
            if isinstance(obj, Value):
                self.add_value(var, obj)

    @abstractmethod
    def write(self, file_path: Optional[Path] = None, factory: bool = False, nondefault: bool = False) -> None:
        ...

    def schedule_on_change(self, key: str, value: Any) -> None:
        for handler in self._on_change:
            self._logger.debug("Postponing property changed callback, key: %s", key)
            if isinstance(handler, weakref.WeakMethod):
                deref_handler = handler()
            else:
                deref_handler = handler
            if not deref_handler:
                continue
            self._stored_callbacks.put(functools.partial(deref_handler, key, value))

    def run_stored_callbacks(self) -> None:
        while not self._stored_callbacks.empty():
            self._stored_callbacks.get()()

    def __setattr__(self, key: str, value: Any):
        object.__setattr__(self, key, value)

        if key.startswith("_"):
            return

        self.schedule_on_change(key, value)
        lock = self._lock.gen_rlock()
        if lock.acquire(blocking=False):
            try:
                self.run_stored_callbacks()
            finally:
                lock.release()

    def add_value(self, var: str, obj: Value) -> Value:
        obj.setup(self, var)
        self._values[var] = obj
        if not var.islower():
            self._lower_to_normal_map[var.lower()] = var
        return obj

    def add_onchange_handler(self, handler: Callable[[str, Any], None]):
        self._on_change.add(weakref.WeakMethod(handler))

    def get_values(self):
        return self._values
