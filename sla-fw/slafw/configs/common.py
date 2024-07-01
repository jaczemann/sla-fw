# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2020-2024 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from copy import deepcopy
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from abc import abstractmethod

from slafw.configs.value import ValueConfig, Value, DictOfConfigs
from slafw.configs.writer import ConfigWriter
from slafw.errors.errors import ConfigException


class ValueConfigCommon(ValueConfig):
    """
    ValueConfigCommon implements all the common stuff for all descendants.

    Value members describe possible configuration options. These can be set using the

    key = value

    notation.
    """
    _add_dict_type = None

    def __init__(
        # pylint: disable=too-many-arguments
        self,
        file_path: Optional[Path] = None,
        factory_file_path: Optional[Path] = None,
        default_file_path: Optional[Path] = None,
        is_master: bool = False,
        force_factory: bool = False,
    ):
        """
        Configuration constructor

        :param file_path: Configuration file path
        :param factory_file_path: Factory configuration file path
        :param default_file_path: default configuration file path (used instead of hardcoded values)
        :param is_master: If True this instance in master, can write to the configuration file
        :param force_factory: If True all writes will be treated as factory writes regardless of other flags
        """
        if factory_file_path is None and file_path is None:
            is_master = True
        super().__init__(is_master=is_master)
        self._file_path = file_path
        self._factory_file_path = factory_file_path
        self._default_file_path = default_file_path
        self._force_factory = force_factory

    def __str__(self) -> str:
        res = [f"{self.__class__.__name__}: {self._file_path} ({self._factory_file_path}) ({self._default_file_path}):"]
        for val in dir(self.__class__):
            o = getattr(self.__class__, val)
            if isinstance(o, Value):
                continue
            if isinstance(o, property):
                res.append(f"\t{val}: {getattr(self, val)}")
        for val,o in self.get_values().items():
            if isinstance(o, DictOfConfigs):
                # TODO handle recursion
                config = self._values[val].value_getter(self)
                if config:
                    res.append(f"\t{val} [{config.idx}]:")
                    for item in config._values:
                        i = config._values[item]
                        value = i.get_value(config)
                        factory = i.get_factory_value(config)
                        default = i.get_default_value(config)
                        v = i.presentation(getattr(config, item))
                        res.append(f"\t\t{item}: {v} ({value}, {factory}, {default})")
            elif isinstance(o, Value):
                value = self._values[val].get_value(self)
                factory = self._values[val].get_factory_value(self)
                default = self._values[val].get_default_value(self)
                res.append(f"\t{val}: {getattr(self, val)} ({value}, {factory}, {default})")
        return "\n".join(res)

    def get_writer(self) -> ConfigWriter:
        """
        Helper to get config writer wrapping this config

        :return: Config writer instance wrapping this config
        """
        return ConfigWriter(self)

    def read_file(self, file_path: Optional[Path] = None) -> None:
        """
        Read config data from config file

        :param file_path: Pathlib path to file
        """
        with self._lock.gen_wlock():
            try:
                if self._default_file_path:
                    if self._default_file_path.exists():
                        self.read_file_raw(self._default_file_path, defaults=True)
                    else:
                        self._logger.info("Defaults config file does not exists: %s", self._default_file_path)
                if self._factory_file_path:
                    if self._factory_file_path.exists():
                        self.read_file_raw(self._factory_file_path, factory=True)
                    else:
                        self._logger.info("Factory config file does not exists: %s", self._factory_file_path)
                if file_path is None:
                    file_path = self._file_path
                if file_path:
                    if file_path.exists():
                        self.read_file_raw(file_path)
                    else:
                        self._logger.info("Config file does not exists: %s", file_path)
            except Exception as exception:
                raise ConfigException("Failed to read configuration files") from exception

    def read_file_raw(self, file_path: Path, factory: bool = False, defaults: bool = False) -> None:
        with file_path.open("r") as f:
            text = f.read()
        try:
            self.read_text(text, factory=factory, defaults=defaults)
        except Exception as exception:
            raise ConfigException(f'Failed to parse config file: "{file_path}"') from exception

    def read_dict(self, data: dict, factory: bool = False, defaults: bool = False) -> None:
        """
        :meta private:
        Read config data from dict

        :param data: dict to import
        :param factory: Whenever to read factory configuration
        """
        self._fill_from_dict(self, self._values.values(), data, factory, defaults)

    def _fill_from_dict(
        # pylint: disable=too-many-arguments
        # pylint: disable=too-many-branches
        self, container, values: list, data: dict, factory: bool = False, defaults: bool = False
    ) -> None:
        processed_data = deepcopy(data)
        for val in values:
            try:
                key = None
                if val.file_key in processed_data:
                    key = val.file_key
                elif val.file_key.lower() in processed_data:
                    key = val.file_key.lower()
                if key is not None:
                    if isinstance(val, DictOfConfigs):
                        self._fill_dict_of_configs(container, processed_data, val, key, factory, defaults)
                    else:
                        v = processed_data[key] if val.unit is None else val.unit(processed_data[key])
                        val.value_setter(container, v, write_override=True, factory=factory, defaults=defaults)
                    del processed_data[key]
            except (KeyError, ConfigException):
                self._logger.exception("Setting config value %s to %s failed", val.name, val)
        if processed_data:
            if self._add_dict_type:
                for key in processed_data:
                    if isinstance(processed_data[key], dict):
                        val = self.add_value(key, DictOfConfigs(self._add_dict_type))
                        config = self._fill_dict_of_configs(container, processed_data, val, key, factory, defaults)
                        setattr(self, key, config)
                    else:
                        self._logger.warning("Extra data in configuration source: %s: %s", key, processed_data[key])
            else:
                self._logger.warning("Extra data in configuration source: \n %s", processed_data)

    def _fill_dict_of_configs(self, container, data: dict, val: Value, key: str, factory: bool, defaults: bool):
        # pylint: disable=too-many-arguments
        config = val.value_getter(container)
        if config is None:
            config = val.type[0]()
        self._fill_from_dict(config, config.get_values().values(), data[key], factory, defaults)
        val.value_setter(container, config, write_override=True, factory=factory, defaults=defaults)
        return config

    @abstractmethod
    def read_text(self, text: str, factory: bool = False, defaults: bool = False) -> None:
        """
        :meta private:
        Read config data from string

        :param text: Config text
        :param factory: Whenever to read factory configuration
        """

    def write(self, file_path: Optional[Path] = None, factory: bool = False, nondefault: bool = False) -> None:
        """
        Write configuration file

        :param file_path: Optional file pathlib Path, default is to save to path set during construction
        :param factory: write as factory config
        """
        with self._lock.gen_rlock():
            if self._force_factory:
                factory = True
            if file_path is None:
                file_path = self._factory_file_path if factory else self._file_path
            self._logger.info("Writing config to %s", file_path)
            try:
                if not self._is_master:
                    raise ConfigException("Cannot save config that is not master")
                data = self._dump_for_save(factory=factory, nondefault=nondefault)
                if not file_path.exists() or file_path.read_text() != data:
                    file_path.write_text(data)
                else:
                    self._logger.info("Skipping config update as no change is to be written")
            except Exception as exception:
                raise ConfigException(f'Cannot save config to: "{file_path}"') from exception

    def write_factory(self, file_path: Optional[Path] = None, nondefault = False) -> None:
        """
        Write factory configuration file
        Alias for write(file_path, factory=True)

        :param file_path: Optional file pathlib Path, default is to save to path set during construction
        """
        self.write(file_path, factory=True, nondefault=nondefault)

    @abstractmethod
    def _dump_for_save(self, factory: bool = False, nondefault: bool = False) -> str:
        """Prepare content of the save file"""

    def as_dictionary(self, nondefault: bool = True, factory: bool = False):
        """
        Get config content as dictionary

        :param nondefault: Return only values that are not set to defaults
        :param factory: Return set of config values that are supposed to be stored in factory config
        """
        return ValueConfigCommon._as_dictionary(self, self._values.values(), nondefault, factory)

    @staticmethod
    def _as_dictionary(container, values: list, nondefault: bool = True, factory: bool = False):
        obj = {}
        for val in values:
            if isinstance(val, DictOfConfigs):
                item = val.value_getter(container)
                next_level = ValueConfigCommon._as_dictionary(item, item.get_values().values(), nondefault, factory)
                if next_level:
                    obj[val.key] = next_level
            elif (not factory or val.factory) and (not val.is_default(container) or nondefault):
                obj[val.key] = val.presentation(val.type[0](val.value_getter(container)))
        return obj

    def factory_reset(self, to_defaults = False) -> None:
        """
        Do factory rest

        This does not save the config. Explict call to save is necessary
        """
        self._logger.info("Running factory reset on config")
        with self._lock.gen_wlock():
            for val in self._values.values():
                if isinstance(val, DictOfConfigs):
                    # TODO handle recursion
                    config = val.value_getter(self)
                    if config:
                        for item in config.get_values().values():
                            item.set_value(config, None)
                            if to_defaults:
                                item.set_factory_value(config, None)
                else:
                    val.set_value(self, None)
                    if to_defaults:
                        val.set_factory_value(self, None)

    def is_factory_read(self) -> bool:
        """
        Require at last one value to have factory default set

        :return: True of factory default were set, False otherwise
        """
        for val in self._values.values():
            if val.get_factory_value(self) is not None:
                return True
        return False

    def get_altered_values(self) -> Dict[str, Tuple[Any, Any]]:
        """
        Get map of altered values

        These values were adjusted from the values set in config according to limits set in the configuration
        specification.

        :return: String -> (adapted, raw) mapping.
        """
        return {
            name: (value.get_value(self), value.get_raw_value(self))
            for name, value in self.get_values().items()
            if value.get_value(self) != value.get_raw_value(self)
        }

    @property
    def factory_file_path(self) -> Path:
        return self._factory_file_path

    @property
    def default_file_path(self) -> Path:
        return self._default_file_path
