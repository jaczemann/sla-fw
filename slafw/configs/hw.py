# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2020-2024 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from slafw import defines
from slafw.configs.ini import IniConfig
from slafw.configs.unit import Nm, Ustep, Ms
from slafw.configs.value import BoolValue, IntValue, FloatValue


class HwConfig(IniConfig):
    # pylint: disable=too-many-instance-attributes
    """
       Hardware configuration is read from /etc/sl1fw/hardware.cfg . Currently the content is parsed using a Toml
       parser with preprocessor that adjusts older custom configuration format if necessary. Members describe
       possible configuration options. These can be set using the

       key = value

       notation. For details see Toml format specification: https://en.wikipedia.org/wiki/TOML
    """


    ######################
    #### TOWER related ###
    ######################

    towerSensitivity = IntValue(0, minimum=-2, maximum=2, factory=True, doc="Tower sensitivity adjustment")
    screwMm = IntValue(4, doc="Pitch of the tower/platform screw. [mm]")
    default_tower_height_mm = IntValue(150, doc="Default tower height. [mm]")
    # Deprecated - use tower_height_nm
    towerHeight = IntValue(
        lambda self: self.nm_to_tower_microsteps(self.default_tower_height_mm * 1_000_000),
        unit=Ustep,
        doc="Maximum tower height. [microsteps]"
    )
    tower_height_nm = IntValue(
        lambda self: self.tower_microsteps_to_nm(self.towerHeight),
        unit=Nm,
        doc="Current tower height. [nanometers]"
    )
    # Deprecated - use calib_tower_offset_nm
    calibTowerOffset = IntValue(
        lambda self: self.nm_to_tower_microsteps(50_000),
        unit=Ustep,
        doc="Adjustment of zero on the tower axis. [microsteps]",
    )
    calib_tower_offset_nm = IntValue(
        lambda self: self.tower_microsteps_to_nm(self.calibTowerOffset),
        unit=Nm,
        doc="Adjustment of zero on the tower axis. [nanometers]",
    )
    tower_calib_position_nm = IntValue(1_000_000, unit=Nm, doc="Tower calibration position. [nanometers]")
    tower_resin_measure_start_nm = IntValue(
        36_000_000,
        unit=Nm,
        doc="Tower start posion for resin measure move. [nanometers]"
    )
    tower_resin_measure_end_nm = IntValue(
        1_000_000,
        unit=Nm,
        doc="Tower end posion for resin measure move. [nanometers]"
    )

    def tower_microsteps_to_nm(self, microsteps: int) -> Nm:
        """
        Covert microsteps to nanometers using the current tower pitch

        :param microsteps: Tower position in microsteps
        :return: Tower position in nanometers
        """
        return Nm(self.tower_microstep_size_nm * microsteps)

    def nm_to_tower_microsteps(self, nanometers: int) -> Ustep:
        """
        Covert nanometers to microsteps using the current tower pitch

        :param nanometers: Tower position in nanometers
        :return: Tower position in microsteps
        """
        return Ustep(nanometers // self.tower_microstep_size_nm)

    @property
    def microStepsMM(self) -> float:
        """
        Get number of microsteps per millimeter using current tower screw pitch.

        :return: Number of microsteps per one millimeter
        """
        return 200 * 16 / int(self.screwMm)

    @property
    def tower_microstep_size_nm(self) -> int:
        """
        Get microstep width in nanometers

        :return: Width in nanometers
        """
        return (self.screwMm * 1000 * 1000) // (200 * 16)


    ####################
    ### TILT related ###
    ####################

    tiltSensitivity = IntValue(0, minimum=-2, maximum=2, doc="Tilt sensitivity adjustment")
    tiltHeight = IntValue(
        4928,   # default is rounded to fullstep (phase 0)
        unit=Ustep,
        doc="Position of the leveled tilt. [ustep]"
    )
    tiltMax = IntValue(
        6016,
        unit=Ustep,
        doc="Max position allowed. It shoud corespond to the top deadlock of the axis. [ustep]"
    )
    tiltMin = IntValue(
        -12800,
        unit=Ustep,
        doc="Position used to ensure the tilt ends at the bottom. [ustep]"
    )
    stirring_moves = IntValue(3, minimum=1, maximum=10, doc="Number of stirring moves")
    stirring_delay_ms = IntValue(500, unit=Ms, minimum=0, maximum=300_000, doc="Delay after stirring.")
    measuringMoves = IntValue(3, minimum=1, maximum=10)
    vatRevision = IntValue(0, minimum=0, maximum=1, doc="Resin vat revision: 0 = metalic (SL1); 1 = plastic (SL1S);")
    forceSlowTiltHeight = IntValue(
        1_000_000,
        minimum=0,
        maximum=10_000_000,
        doc="Force slow tilt after crossing area_fill for defined height. [nm]"
    )


    #######################
    ### UP&DOWN related ###
    #######################

    up_and_down_uv_on = BoolValue(False, doc="Keep UV LED on during Up&Down.")
    up_and_down_wait = IntValue(10, minimum=0, maximum=600, doc="Up&Down wait time. [seconds]")
    up_and_down_every_layer = IntValue(0, minimum=0, maximum=500, doc="Do Up&Down every N layers, 0 means never.")
    up_and_down_z_offset_nm = IntValue(
        0,
        unit=Nm,
        minimum=-5_000_000,
        maximum=5_000_000,
        doc="Tower position shift after Up&Down."
    )
    up_and_down_expo_comp_ms = IntValue(
        0,
        unit=Ms,
        minimum=-10_000,
        maximum=30_000,
        doc="Exposure time shift after Up&Down."
    )


    ####################
    ### FANS related ###
    ####################

    fanCheck = BoolValue(True, doc="Check fan function if set to True.")
    fan1Rpm = IntValue(
        2000,
        minimum=defines.fanMinRPM,
        maximum=defines.fanMaxRPM[0],
        factory=True,
        doc="UV LED fan RPMs."
    )
    fan2Rpm = IntValue(
        3300,
        minimum=defines.fanMinRPM,
        maximum=defines.fanMaxRPM[1],
        factory=True,
        doc="Blower fan RPMs."
    )
    fan3Rpm = IntValue(
        1000,
        minimum=defines.fanMinRPM,
        maximum=defines.fanMaxRPM[2],
        factory=True,
        doc="Rear fan RPMs."
    )
    fan1Enabled = BoolValue(True, doc="UV LED fan status.")
    fan2Enabled = BoolValue(True, doc="Blower fan status.")
    fan3Enabled = BoolValue(True, doc="Rear fan status.")
    rpmControlUvLedMinTemp = IntValue(
        defines.minAmbientTemp,
        minimum=0,
        maximum=80,
        doc="At this temperature UV LED fan will spin at the minimum RPM."
    )
    rpmControlUvLedMaxTemp = IntValue(
        defines.maxUVTemp - 5,
        minimum=0,
        maximum=80,
        doc="At this temperature UV LED fan will spin at the maximum RPM."
    )
    rpmControlUvFanMinRpm = IntValue(
        defines.fanMinRPM,
        minimum=defines.fanMinRPM,
        maximum=defines.fanMaxRPM[0],
        doc="RPM is lineary mapped to UV LED temp. This is the lower limit.."
    )
    rpmControlUvFanMaxRpm = IntValue(
        defines.fanMaxRPM[0],
        minimum=defines.fanMinRPM,
        maximum=defines.fanMaxRPM[0],
        doc="RPM is lineary mapped to UV LED temp. This is the upper limit."
    )
    rpmControlUvEnabled = BoolValue(
        True,
        doc="Control UV FAN RPM by UV LED temp. If false use the RPM set in this config."
    )


    #######################
    ### UV LEDs related ###
    #######################

    uvCurrent = FloatValue(0.0, minimum=0.0, maximum=800.0, doc="UV LED current, DEPRECATED.")
    uvPwmTune = IntValue(0, minimum=-10, maximum=10, doc="Fine tune UV PWM. This value is added to standard uvPwm [-]")
    uvPwm = IntValue(
        lambda self: int(round(self.uvCurrent / 3.2)),
        minimum=0,
        maximum=250,
        factory=True,
        doc="UV LED PWM set by UV calibration (SL1) or calculated (SL1s) [-].",
    )
    uvWarmUpTime = IntValue(120, minimum=0, maximum=300, doc="UV LED calibration warmup time. [seconds]")
    uvCalibIntensity = IntValue(140, minimum=90, maximum=200, doc="UV LED calibration intensity.")
    uvCalibMinIntEdge = IntValue(90, minimum=80, maximum=150, doc="UV LED calibration minimum intensity at the edge.")
    uvCalibBoostTolerance = IntValue(20, minimum=0, maximum=100, doc="Tolerance for allowing boosted results.")

    @property
    def uvPwmPrint(self) -> int:
        """
        Final UV PWM used for printing

        :return: Value which is supposed to be used for printing
        """
        return self.uvPwm + self.uvPwmTune


    ####################################
    ### TANK CLEANING WIZARD related ###
    ####################################

    tankCleaningExposureTime = IntValue(
        0,
        minimum=5,
        maximum=120,
        doc="Exposure time when running the tank surface cleaning wizard."
        "Default 0 needs to be overwritten once the printer model is known."
    )
    tankCleaningGentlyUpProfile = IntValue(
        1,
        minimum=0,
        maximum=3,
        doc="Select the profile used for the upward movement of the platform in the tank surface cleaning wizard "
        "(should be cast into GentlyUpProfile enum)."
    )
    tankCleaningMinDistance_nm = IntValue(
        100_000,
        unit=Nm,
        minimum=0,
        maximum=5_000_000,
        doc="Distance of the garbage collector from the resin tank bottom when moving down."
    )
    tankCleaningAdaptorHeight_nm = IntValue(
        25_000_000,
        unit=Nm,
        minimum=3_000_000,
        maximum=200_000_000,
        doc="Expected cleaning adapter height, the platform will descend at most 3mm below this height"
    )


    #############
    ### OTHER ###
    #############

    pwrLedPwm = IntValue(100, minimum=0, maximum=100, doc="Power LED brightness. [%]")
    coverCheck = BoolValue(True, doc="Check for closed cover during printer movements and exposure if set to True.")
    MCversionCheck = BoolValue(True, doc="Check motion controller firmware version if set to True.")
    resinSensor = BoolValue(True, doc="If True the the resin sensor will be used to measure resin level before print.")
    autoOff = BoolValue(True, doc="If True the printer will be shut down after print.")
    mute = BoolValue(False, doc="Mute motion controller speaker if set to True.")
    showWizard = BoolValue(True, doc="Display wizard at startup if True.")
    showUnboxing = BoolValue(True, doc="Display unboxing wizard at startup if True.")
    raw_calibrated = BoolValue(False, key="calibrated")

    @property
    def calibrated(self) -> bool:
        """
        Printer calibration state

        The value can read as False when set to True as further requirements on calibration are checked in the getter.

        :return: True if printer is calibrated, False otherwise
        """
        # TODO: Throw away raw_calibrated, judge calibrated based on tilt/tower height
        return self.raw_calibrated and int(self.tiltHeight) % 64 == 0

    @calibrated.setter
    def calibrated(self, value: bool) -> None:
        self.raw_calibrated = value

    data_privacy = BoolValue(True, doc="Defines if help page URL should contain machines unique fingerprint.")
