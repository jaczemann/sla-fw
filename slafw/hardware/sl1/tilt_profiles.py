# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from slafw import defines
from slafw.configs.value import DictOfConfigs
from slafw.hardware.tilt import MovingProfilesTilt
from slafw.hardware.sl1.axis import SingleProfileSL1


TILT_CFG_LOCAL = defines.configDir / "profiles_tilt.json"


class MovingProfilesTiltSL1(MovingProfilesTilt):
    # pylint: disable=too-many-ancestors
    homingFast = DictOfConfigs(SingleProfileSL1)      # type: ignore
    homingSlow = DictOfConfigs(SingleProfileSL1)      # type: ignore
    move120 = DictOfConfigs(SingleProfileSL1)         # type: ignore
    layer200 = DictOfConfigs(SingleProfileSL1)        # type: ignore
    move300 = DictOfConfigs(SingleProfileSL1)         # type: ignore
    layer400 = DictOfConfigs(SingleProfileSL1)        # type: ignore
    layer600 = DictOfConfigs(SingleProfileSL1)        # type: ignore
    layer800 = DictOfConfigs(SingleProfileSL1)        # type: ignore
    layer1000 = DictOfConfigs(SingleProfileSL1)       # type: ignore
    layer1250 = DictOfConfigs(SingleProfileSL1)       # type: ignore
    layer1500 = DictOfConfigs(SingleProfileSL1)       # type: ignore
    layer1750 = DictOfConfigs(SingleProfileSL1)       # type: ignore
    layer2000 = DictOfConfigs(SingleProfileSL1)       # type: ignore
    layer2250 = DictOfConfigs(SingleProfileSL1)       # type: ignore
    move5120 = DictOfConfigs(SingleProfileSL1)        # type: ignore
    move8000 = DictOfConfigs(SingleProfileSL1)        # type: ignore
    __definition_order__ = tuple(locals())
