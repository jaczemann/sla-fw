# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from slafw import defines
from slafw.configs.value import DictOfConfigs
from slafw.hardware.tower import MovingProfilesTower
from slafw.hardware.sl1.axis import SingleProfileSL1


TOWER_CFG_LOCAL = defines.configDir / "profiles_tower.json"


class MovingProfilesTowerSL1(MovingProfilesTower):
    # pylint: disable=too-many-ancestors
    homingFast = DictOfConfigs(SingleProfileSL1)  # type: ignore
    homingSlow = DictOfConfigs(SingleProfileSL1)  # type: ignore
    moveFast = DictOfConfigs(SingleProfileSL1)    # type: ignore
    moveSlow = DictOfConfigs(SingleProfileSL1)    # type: ignore
    resinSensor = DictOfConfigs(SingleProfileSL1) # type: ignore
    layer1 = DictOfConfigs(SingleProfileSL1)      # type: ignore
    layer2 = DictOfConfigs(SingleProfileSL1)      # type: ignore
    layer3 = DictOfConfigs(SingleProfileSL1)      # type: ignore
    layer4 = DictOfConfigs(SingleProfileSL1)      # type: ignore
    layer5 = DictOfConfigs(SingleProfileSL1)      # type: ignore
    layer8 = DictOfConfigs(SingleProfileSL1)      # type: ignore
    layer11 = DictOfConfigs(SingleProfileSL1)     # type: ignore
    layer14 = DictOfConfigs(SingleProfileSL1)     # type: ignore
    layer18 = DictOfConfigs(SingleProfileSL1)     # type: ignore
    layer22 = DictOfConfigs(SingleProfileSL1)     # type: ignore
    layer24 = DictOfConfigs(SingleProfileSL1)     # type: ignore


    __definition_order__ = tuple(locals())
