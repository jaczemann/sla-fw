# This file is part of the SLA firmware
# Copyright (C) 2022-2024 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from slafw.configs.json import JsonConfig
from slafw.configs.value import DictOfConfigs, BoolValue, IntValue, ProfileIndex
from slafw.configs.unit import Ustep, Nm, Ms
from slafw.hardware.profiles import SingleProfile
from slafw.hardware.sl1.tilt_profiles import MovingProfilesTiltSL1
from slafw.hardware.sl1.tower_profiles import MovingProfilesTowerSL1


EXPOSURE_PROFILES_DEFAULT_NAME = "_default_exposure_profile.json"


class SingleLayerProfileSL1(SingleProfile):
    delay_before_exposure_ms = IntValue(
            minimum=0,
            maximum=30_000,
            unit=Ms,
            factory=True,
            doc="Delay between tear off and exposure.")
    delay_after_exposure_ms = IntValue(
            minimum=0,
            maximum=30_000,
            unit=Ms,
            factory=True,
            doc="Delay between exposure and tear off.")
    tower_hop_height_nm = IntValue(
            minimum=0,
            maximum=100_000_000,
            unit=Nm,
            factory=True,
            doc="How much to raise the tower during layer change.")
    tower_profile = ProfileIndex(
            MovingProfilesTowerSL1,
            factory=True,
            doc="The tower moving profile.")
    use_tilt = BoolValue(
            factory=True,
            doc="Use the tilt to tear off the layers.")
    # tilt down settings
    tilt_down_initial_profile = ProfileIndex(
            MovingProfilesTiltSL1,
            factory=True,
            doc="The tilt profile for first move down.")
    tilt_down_offset_steps = IntValue(
            minimum=0,
            maximum=10000,
            unit=Ustep,
            factory=True,
            doc="How many steps to perform in first move down.")
    tilt_down_offset_delay_ms = IntValue(
            minimum=0,
            maximum=20000,
            unit=Ms,
            factory=True,
            doc="Waiting time after first move down.")
    tilt_down_finish_profile = ProfileIndex(
            MovingProfilesTiltSL1,
            factory=True,
            doc="The tilt profile for remaining moves down.")
    tilt_down_cycles = IntValue(
            minimum=0,
            maximum=10,
            factory=True,
            doc="How many parts should the remaining distance be made up of.")
    tilt_down_delay_ms = IntValue(
            minimum=0,
            maximum=20000,
            unit=Ms,
            factory=True,
            doc="Waiting time after every part.")
    # tilt up settings
    tilt_up_initial_profile = ProfileIndex(
            MovingProfilesTiltSL1,
            factory=True,
            doc="The tilt profile for first move up.")
    tilt_up_offset_steps = IntValue(
            minimum=0,
            maximum=10000,
            unit=Ustep,
            factory=True,
            doc="How many steps to perform in first move up.")
    tilt_up_offset_delay_ms = IntValue(
            minimum=0,
            maximum=20_000,
            unit=Ms,
            factory=True,
            doc="Waiting time after first move up.")
    tilt_up_finish_profile = ProfileIndex(
            MovingProfilesTiltSL1,
            factory=True,
            doc="The tilt profile for remaining moves up.")
    tilt_up_cycles = IntValue(
            minimum=0,
            maximum=10,
            factory=True,
            doc="How many parts should the remaining distance be made up of.")
    tilt_up_delay_ms = IntValue(
            minimum=0,
            maximum=20_000,
            unit=Ms,
            factory=True,
            doc="Waiting time after every part.")

    __definition_order__ = tuple(locals())


class ExposureProfileSL1(JsonConfig):
    area_fill = IntValue(45)
    below_area_fill = DictOfConfigs(SingleLayerProfileSL1)
    above_area_fill = DictOfConfigs(SingleLayerProfileSL1)
    _add_dict_type = SingleLayerProfileSL1 # type: ignore
