# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2020-2021 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

import toml


class TomlConfig:
    def __init__(self, filename=None):
        self.logger = logging.getLogger(__name__)
        self.filename = filename
        self.data = {}

    def load(self):
        try:
            if not self.filename:
                raise Exception("No filename specified")
            with open(self.filename, "r", encoding="utf-8") as f:
                self.data = toml.load(f)
        except FileNotFoundError:
            self.logger.warning("File '%s' not found", self.filename)
            self.data = {}
        except Exception:
            self.logger.exception("Failed to load toml file")
            self.data = {}
        return self.data

    def save_raw(self):
        if not self.filename:
            raise Exception("No filename specified")
        with open(self.filename, "w", encoding="utf-8") as f:
            toml.dump(self.data, f)

    def save(self, data=None, filename=None):
        try:
            if data:
                self.data = data
            if filename:
                self.filename = filename
            self.save_raw()
        except Exception:
            self.logger.exception("Failed to save toml file")
            return False
        return True
