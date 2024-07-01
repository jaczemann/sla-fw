# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2020-2021 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
from typing import Dict, Any, Set

from slafw.configs.value import ValueConfig

# This is to avoid random false positives reported by pylint
# pylint: disable = too-many-instance-attributes


class ConfigWriter:
    """
    Class used as helper for transactional config writing

    The class mimics underlying config class attributes for value reading ang writting. The changes are propagated
    to underlying config on commit.
    """

    def __init__(self, config: ValueConfig):
        """
        Config writer constructor

        :param config: Underling configuration object
        """
        self._logger = logging.getLogger(__name__)
        self._config = config
        self._changed: Dict[str, Any] = {}
        self._deleted: Set[str] = set()

    def _get_attribute_name(self, key: str) -> str:
        """
        Adjust attribute name in case of legacy lowcase name

        :param key: Low-case or new key
        :return: Valid key
        """
        if key in vars(self._config) or key in vars(self._config.__class__):
            return key
        normalized_key = self._config.lower_to_normal_map(key)
        if normalized_key:
            self._logger.warning("Config setattr using fallback low-case name: %s", key)
            return normalized_key
        raise AttributeError(f'Key: "{key}" not in config')

    def __getattr__(self, item: str):
        item = self._get_attribute_name(item)
        if item in self._changed:
            return self._changed[item]
        if item in self._deleted:
            if item in self._config.get_values():
                value = self._config.get_values()[item]
                if value.get_factory_value(self._config) is not None:
                    return value.get_factory_value(self._config)
                return value.get_default_value(self._config)
            return None
        return getattr(self._config, item)

    def __setattr__(self, key, value):
        if key.startswith("_"):
            object.__setattr__(self, key, value)
            return

        key = self._get_attribute_name(key)
        if key in self._config.get_values():
            config_value = self._config.get_values()[key]
            config_value.value_setter(self._config, value, dry_run=True)
            old = value
            value = config_value.adapt(value)
            if old != value:
                self._logger.warning("Adapting config value %s from %s to %s", key, old, value)
        else:
            self._logger.debug("Writer: Skipping dry run write on non-value: %s", key)

        # Update changed or reset it if change is returning to original value
        if value == getattr(self._config, key):
            if key in self._changed:
                del self._changed[key]
        else:
            self._changed[key] = value

    def __delattr__(self, item):
        item = self._get_attribute_name(item)
        self._deleted.add(item)

    def update(self, values: Dict[str, Any]):
        for key, val in values.items():
            self.__setattr__(key, val)

    def commit_dict(self, values: Dict):
        self.update(values)
        self.commit()

    def commit(self, write: bool = True, factory: bool = False):
        """
        Save changes to underlying config and write it to file

        :param: write Whenever to write configuration file
        """
        # Skip everything in case of no changes
        if not self.changed():
            self._logger.info("Skipping update with empty changes")
            return

        # Update values with write lock
        with self._config.lock.gen_wlock():
            for key, val in self._changed.items():
                if key in self._config.get_values():
                    self._config.get_values()[key].value_setter(self._config, val)
                else:
                    setattr(self._config, key, val)
            for key in self._deleted:
                delattr(self._config, key)

        if write:
            self._config.write(factory=factory)

        # Run notify callbacks with write lock unlocked
        for key, val in self._changed.items():
            self._config.schedule_on_change(key, val)
        self._config.run_stored_callbacks()

        self._changed = {}

    def changed(self, key=None):
        """
        Test for changes relative to underlying config.

        :param key: Test only for specific key. If not specified or None changes on all keys are checked.
        :return: True if changed, false otherwise
        """
        if key is None:
            return bool(self._changed) or bool(self._deleted)
        return key in self._changed or key in self._deleted

    def reset(self):
        """
        Reset changed values to original

        :return: None
        """
        self._changed = {}
        self._deleted = set()

    def get_value_property(self, item: str, prop: str):
        item = self._get_attribute_name(item)
        value = self._config.get_values().get(item, None)
        return getattr(value, prop, None)
