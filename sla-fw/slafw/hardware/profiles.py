# This file is part of the SLA firmware
# Copyright (C) 2022-2024 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path
from typing import Optional, Callable, List
from functools import cache # type: ignore
from abc import abstractmethod

from slafw.configs.common import ValueConfigCommon
from slafw.configs.json import JsonConfig
from slafw.configs.writer import ConfigWriter
from slafw.errors.errors import ConfigException


class SingleProfile(ValueConfigCommon):
    @property
    @abstractmethod
    def __definition_order__(self) -> tuple:
        """defined items order"""

    def __init__(self):
        super().__init__(is_master=True)
        self.name: Optional[str] = None
        self.idx: Optional[int] = None
        self.saver: Optional[Callable] = None

    def __iter__(self):
        for name in self.__definition_order__:
            if not name.startswith("_"):
                yield self._values[name]

    def __eq__(self, other):
        if isinstance(other, SingleProfile):
            return list(self.dump()) == list(other.dump())
        if isinstance(other, list):
            return list(self.dump()) == other
        return False

    def dump(self):
        for value in self:
            yield value.value_getter(self)

    def get_writer(self) -> ConfigWriter:
        return ConfigWriter(self)

    def write(self, file_path: Optional[Path]=None, factory: bool=False, nondefault: bool=False) -> None:
        if not callable(self.saver):
            raise ConfigException("Write fuction not defined")
        self.saver(file_path, factory, nondefault)  # pylint: disable=not-callable

    @property
    def is_modified(self):
        for val in self._values.values():
            if val.get_factory_value(self) is not None:
                return True
        return False

    def _dump_for_save(self, factory: bool = False, nondefault: bool = False) -> str:
        raise NotImplementedError

    def read_text(self, text: str, factory: bool = False, defaults: bool = False) -> None:
        raise NotImplementedError


class ProfileSet(JsonConfig):
    @property
    @abstractmethod
    def __definition_order__(self) -> tuple:
        """defined items order"""

    @property
    @abstractmethod
    def name(self) -> str:
        """profile set name"""

    def __init__(
            self,
            file_path: Optional[Path]=None,
            factory_file_path: Optional[Path]=None,
            default_file_path: Optional[Path]=None
    ):
        self._apply_profile: Optional[Callable] = None
        self._ordered_profiles: List[SingleProfile] = []
        super().__init__(
                file_path=file_path,
                factory_file_path=factory_file_path,
                default_file_path=default_file_path
        )

        idx = 0
        for name in self.__definition_order__:
            if not name.startswith("_"):
                self._add_profile(name, idx)
                idx += 1
        for name in sorted(self.get_values()):
            if name not in self.__definition_order__:
                self._add_profile(name, idx)
                self._logger.info("Profile '%s' added from config file as index %d", name, idx)
                idx += 1

    def _add_profile(self, name: str, idx: int):
        profile = getattr(self, name)
        if profile is None:
            raise ConfigException(f"Missing data for profile <{name}>")
        for value in profile:
            if value.value_getter(profile) is None:
                raise ConfigException(f"Missing data for value <{value.key}> in profile <{name}>")
        profile.name = name
        profile.idx = idx
        profile.saver = self.write
        self._ordered_profiles.append(profile)

    def __iter__(self):
        for profile in self._ordered_profiles:
            yield profile

    def __len__(self):
        return len(self._ordered_profiles)

    @cache
    def __getitem__(self, idx):
        return self._ordered_profiles[idx]

    def apply_all(self):
        if callable(self._apply_profile):
            for profile in self:
                self._apply_profile(profile)

    @property
    def apply_profile(self) -> Callable:
        return self._apply_profile

    @apply_profile.setter
    def apply_profile(self, callback: Callable):
        self._apply_profile = callback
