# This file is part of the SLA firmware
# Copyright (C) 2021-2024 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from PySignal import Signal

from slafw.project.project import ProjectData

class Project:
    # pylint: disable = too-few-public-methods
    # pylint: disable = too-many-instance-attributes
    def __init__(self):
        self.data = ProjectData(changed = Signal(), path = "/nice/path/file.suffix")
        self.name = "Nice name"
        self.used_material_nl = 45242420
        self.total_layers = 4242
        self.layer_height_nm = 50000
        self.layer_height_first_nm = self.layer_height_nm
        self.total_height_nm = self.total_layers * self.layer_height_nm
