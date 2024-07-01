# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import pprint
from slafw.configs.toml import TomlConfig

class SlicerProfile(TomlConfig):

    def __str__(self) -> str:
        pp = pprint.PrettyPrinter(width=200)
        return pp.pformat(self.data)

    @property
    def vendor(self) -> dict:
        return self.data['vendor']

    @vendor.setter
    def vendor(self, value: dict) -> None:
        self.data['vendor'] = value

    @property
    def printer(self) -> dict:
        return self.data['printer']

    @printer.setter
    def printer(self, value: dict) -> None:
        self.data['printer'] = value
