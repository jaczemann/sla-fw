# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2020-2024 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import json
from pathlib import Path
from typing import Optional

from slafw.configs.common import ValueConfigCommon
from slafw.errors.errors import ConfigException


class JsonConfig(ValueConfigCommon):
    """
    Main config class based on JSON files.

    Inherit this to create a JSON configuration
    """
    def __init__(
            self,
            file_path: Optional[Path] = None,
            factory_file_path: Optional[Path] = None,
            default_file_path: Optional[Path] = None
    ):
        super().__init__(
                file_path=file_path,
                factory_file_path=factory_file_path,
                default_file_path=default_file_path,
                is_master=True,
                force_factory=True,
        )
        self.read_file()

    def read_text(self, text: str, factory: bool = False, defaults: bool = False) -> None:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exception:
            raise ConfigException(f"Failed to decode config content:\n {text}") from exception
        self._fill_from_dict(self, self._values.values(), data, factory, defaults)

    def _dump_for_save(self, factory: bool = False, nondefault: bool = False) -> str:
        return json.dumps(self.as_dictionary(nondefault=nondefault, factory=factory), indent=4)
