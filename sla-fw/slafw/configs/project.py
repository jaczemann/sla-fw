# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2024 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

# TODO: Fix following pylint problems
# pylint: disable=too-many-instance-attributes

from abc import ABC
from enum import Enum

from slafw.configs.ini import IniConfig
from slafw.configs.json import JsonConfig
from slafw.configs.value import FloatValue, IntValue, TextValue, BoolValue, FloatListValue, DictOfConfigs
from slafw import defines
from slafw.exposure.profiles import ExposureProfileSL1


class ExpUserProfile(Enum):
    fast = 0
    slow = 1
    high_viscosity = 2


class ProjectConfigBase(ABC):
    # pylint: disable = too-few-public-methods
    """
    Project configuration is read from config.ini located in the project zip file. Currently the content is parsed using
    a Toml parser with preprocessor that adjusts older custom configuration format if necessary. Members describe
    possible configuration options. These can be set using the

    key = value

    notation. For details see Toml format specification: https://en.wikipedia.org/wiki/TOML
    """

    job_dir = TextValue("no project", key="jobDir", doc="Name of the directory containing layer images.")

    expTime = FloatValue(
        8.0,
        minimum=0.1,
        maximum=60.0,
        doc="Exposure time. [s]"
    )
    expTimeFirst = FloatValue(
        35.0,
        minimum=0.1,
        maximum=120.0,
        doc="First layer exposure time. [s]"
    )
    # TODO - use profile names!
    expUserProfile = IntValue(
        0,
        minimum=0,
        doc="Identifies set of exposure settings. "
            "0 - fast"
            "1 - slow - slower tilt, delay before exposure"
            "2 - high viscosity - very slow, tower z hop, longer delay before exposure"
            "3+ other custom profiles"
    )
    layerHeight = FloatValue(-1, doc="Layer height, if not equal to -1 supersedes stepNum. [mm]")
    stepnum = IntValue(40, doc="Layer height [microsteps]")
    layerHeightFirst = FloatValue(0.05)
    fadeLayers = IntValue(
        10,
        minimum=2,
        maximum=200,
        key="numFade",
        doc="""Number of layers used for transition from first layer exposure time to standard exposure time and
            elephant foot compensation.

            CAUTION! Keep in mind that Prusa Slicer counterintuitively includes both the `Initial exposure time`
            layer and standard `Exposure times` layer into the `Faded layers`.

            For example with settings:

            - Faded layers = 5
            - Initial exposure time = 10 s
            - Exposure time = 1 s
            - Elephant foot compensation = 1 mm

            results in:

            - 1st layer is compensated the most (by 1 mm) and exposed for 10 s.
            - 2nd to 4th layers are proportionally elephant foot compensated (by 0.75, 0.5 and 0.25 mm) and exposed \
            for 7.75, 5.5 and 3.25 s.
            - 5th layer is NOT compensated and exposed by standard Exposure time for 1 s."""
    )

    calibrateRegions = IntValue(0, doc="Number of calibration regions (2, 4, 6, 8, 9, 10), 0 = off")
    calibrateTime = FloatValue(
        1.0,
        minimum=0.1,
        maximum=5.0,
        doc="Time added to exposure per calibration region. [seconds]"
    )
    calibrateTimeExact = FloatListValue(
        [], doc="Force calibration times with these values, for all layers!"
    )
    calibrateCompact = BoolValue(
        False, doc="Do not generate labels and group regions in the center of the display if set to True."
    )
    calibrateTextSize = FloatValue(
        5.0, doc="Size of the text on calibration label. [millimeters]"
    )
    calibrateTextThickness = FloatValue(
        0.5, doc="Thickness of the text on calibration label. [millimeters]"
    )
    calibratePadSpacing = FloatValue(
        1.0, doc="Spacing of the pad around the text. [millimeters]"
    )
    calibratePadThickness = FloatValue(
        0.5, doc="Thickness of the pad of the calibration label. [millimeters]"
    )
    calibratePenetration = FloatValue(
        0.5, doc="How much to sink the calibration label into the object. [millimeters]"
    )

    usedMaterial = FloatValue(
        defines.resinMaxVolume - defines.resinMinVolume,
        doc="Resin necessary to print the object. Default is full tank. [milliliters]",
    )
    layersSlow = IntValue(0, key="numSlow", doc="Number of layers that require slow tear off.")
    layersFast = IntValue(0, key="numFast", doc="Number of layers that do not require slow tear off.")

    action = TextValue(doc="What to do with the project. Legacy value, currently discarded.")
    raw_modification_time = TextValue(
            None, key="fileCreationTimestamp", doc="Date and time of project creation [YYYY-MM-DD at HH:MM:SS TZ]")

    printProfile = TextValue(doc="Print settings used for slicing, currently discarded.")
    materialName = TextValue(doc="Material used for slicing, currently discarded.")
    printerProfile = TextValue(doc="Printer settings used for slicing, currently discarded.")
    printerModel = TextValue("SL1", doc="Printer model project is sliced for.")
    printerVariant = TextValue("default", doc="Printer variant project is sliced for.")
    printTime = FloatValue(0.0, doc="Project print time, currently discarded (calculated by fw) [seconds]")
    prusaSlicerVersion = TextValue(doc="Slicer used for slicing, currently discarded.")


class ProjectConfig(ProjectConfigBase, IniConfig):
    def __init__(self):
        super().__init__(is_master=True)


class ProjectConfigJson(ProjectConfigBase, JsonConfig):
    version = IntValue(1, doc="Version of the config file. The version specifies which parameters are expected.")
    exposure_profile = DictOfConfigs(ExposureProfileSL1)
