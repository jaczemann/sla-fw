# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2020-2021 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import subprocess
from slafw.configs.toml import TomlConfig
from slafw.hardware.hardware import BaseHardware


class TomlConfigStatsException(Exception):
    pass


class TomlConfigStats(TomlConfig):
    def __init__(self, filename, hw: BaseHardware):
        super(TomlConfigStats, self).__init__(filename)
        self.hw = hw

    def load(self):
        super(TomlConfigStats, self).load()
        if "projects" in self.data:
            self.data["started_projects"] = self.data.get("started_projects", self.data.get("projects", 0))
            self.data["finished_projects"] = self.data.get("finished_projects", self.data.get("projects", 0))
            del self.data["projects"]
        return self.data

    def update_reboot_counter(self):
        try:
            result = subprocess.run(["uptime", "-s"], capture_output=True, check=True)
            system_up_since = result.stdout.decode("ascii").strip()
            self.load()
            if self["last_reboot"] != system_up_since:
                self["last_reboot"] = system_up_since
                self["reboot_counter"] += 1
                self.save_raw()
        except Exception as exception:
            raise TomlConfigStatsException from exception

    def __setitem__(self, key, value):
        self.data[key] = value

    def __delitem__(self, key):
        if key in self.data:
            del self.data[key]
            return
        raise KeyError(key)

    def __getitem__(self, key):
        if key in self.data:
            return self.data[key]

        if key == "total_seconds":
            return self.hw.uv_led.usage_s

        if key in ["started_projects", "finished_projects"]:
            return self.data.get("projects", 0)

        return 0
