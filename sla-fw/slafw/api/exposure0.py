# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2024 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from enum import unique, Enum
from typing import Any, Dict

from pydbus.generic import signal

from slafw import defines
from slafw.api.decorators import (
    dbus_api,
    DBusObjectPath,
    auto_dbus,
    state_checked,
    range_checked,
    wrap_dict_data,
    auto_dbus_signal,
)
from slafw.errors.errors import (
    PrinterException,
)
from slafw.errors.warnings import PrinterWarning
from slafw.exposure.exposure import Exposure
from slafw.project.project import LayerProfileTuple
from slafw.states.exposure import ExposureState


@unique
class Exposure0State(Enum):
    """
    Exposure state enumeration
    """

    INIT = 0
    PRINTING = 1
    GOING_UP = 2
    GOING_DOWN = 3
    WAITING = 4
    COVER_OPEN = 5
    FEED_ME = 6
    FAILURE = 7
    STIRRING = 9
    PENDING_ACTION = 10
    FINISHED = 11
    STUCK = 12
    STUCK_RECOVERY = 13
    READING_DATA = 14
    CONFIRM = 15
    CHECKS = 16
    TILTING_DOWN = 19
    CANCELED = 20
    CHECK_WARNING = 23
    DONE = 24
    OVERHEATING = 25
    POUR_IN_RESIN = 26
    HOMING_AXIS = 27

    @staticmethod
    def from_exposure(state: ExposureState) -> Exposure0State:
        return {
            ExposureState.INIT: Exposure0State.INIT,
            ExposureState.PRINTING: Exposure0State.PRINTING,
            ExposureState.GOING_UP: Exposure0State.GOING_UP,
            ExposureState.GOING_DOWN: Exposure0State.GOING_DOWN,
            ExposureState.WAITING: Exposure0State.WAITING,
            ExposureState.COVER_OPEN: Exposure0State.COVER_OPEN,
            ExposureState.FEED_ME: Exposure0State.FEED_ME,
            ExposureState.FAILURE: Exposure0State.FAILURE,
            ExposureState.STIRRING: Exposure0State.STIRRING,
            ExposureState.PENDING_ACTION: Exposure0State.PENDING_ACTION,
            ExposureState.FINISHED: Exposure0State.FINISHED,
            ExposureState.STUCK: Exposure0State.STUCK,
            ExposureState.STUCK_RECOVERY: Exposure0State.STUCK_RECOVERY,
            ExposureState.READING_DATA: Exposure0State.READING_DATA,
            ExposureState.CONFIRM: Exposure0State.CONFIRM,
            ExposureState.CHECKS: Exposure0State.CHECKS,
            ExposureState.TILTING_DOWN: Exposure0State.TILTING_DOWN,
            ExposureState.CANCELED: Exposure0State.CANCELED,
            ExposureState.CHECK_WARNING: Exposure0State.CHECK_WARNING,
            ExposureState.DONE: Exposure0State.DONE,
            ExposureState.COOLING_DOWN: Exposure0State.OVERHEATING,
            ExposureState.POUR_IN_RESIN: Exposure0State.POUR_IN_RESIN,
            ExposureState.HOMING_AXIS: Exposure0State.HOMING_AXIS,
        }[state]


@dbus_api
class Exposure0:
    """
    Exposure D-Bus interface

    This is first draft. This should contain all data current pages do contain plus some new stuff that should be enough
    to mimic wait pages and similar stuff.

    Most of the functions should be deprecated and replaced by ones returning values in sane units.
    remaining minutes -> expected end timestamp, ...

    # Error handling
    Errors and exception come with data dictionary that is supposed to include at last a "code" member pointing to a
    standard Prusa error code.

    - Errors resulting from DBus calls are reported as native DBus errors. Exception data dictionary is embedded as json
      into a DBus error message.
    - Non-fatal errors produced by exposure internal thread (problems encountered during print) are reported using an
      exception signal. The signal includes error message data dictionary.
    - Fatal error that crashed the internal thread (fatal error that stopped the print) is stored in failure_reason
      property including data dictionary.
    """

    # This class is an API to the exposure process. As the API is a draft it turned out to have many methods. Let's
    # disable the pylint warning about this, but keep in mind to reduce the interface in next API revision.
    # pylint: disable=too-many-public-methods

    __INTERFACE__ = "cz.prusa3d.sl1.exposure0"
    PropertiesChanged = signal()

    @staticmethod
    def dbus_path(instance_id) -> DBusObjectPath:
        return DBusObjectPath(f"/cz/prusa3d/sl1/exposures0/{instance_id}")

    def __init__(self, exposure: Exposure):
        self.exposure = exposure
        self._logger = logging.getLogger(__name__)

        # Do not use lambdas as handlers. These would keep references to Exposure0
        self.exposure.data.changed.connect(self._handle_exposure_change)
        if self.exposure.hw:
            self.exposure.hw.cover_state_changed.connect(self._handle_cover_change_param)
        if self.exposure.hw.config:
            self.exposure.hw.config.add_onchange_handler(self._handle_config_change)
        if self.exposure.warning_occurred:
            self.exposure.warning_occurred.connect(self._on_warning_occurred)

    @auto_dbus_signal
    def exception(self, value: Dict[str, Any]):
        pass

    @auto_dbus_signal
    def about_to_be_deleted(self):
        pass

    def _on_warning_occurred(self, warning: Warning):
        self.exception(wrap_dict_data(PrinterWarning.as_dict(warning)))

    @auto_dbus
    @property
    def failure_reason(self) -> Dict[str, Any]:
        return wrap_dict_data(PrinterException.as_dict(self.exposure.data.fatal_error))

    @auto_dbus
    @state_checked(Exposure0State.CONFIRM)
    def confirm_start(self) -> None:
        """
        Confirm exposure start

        :return: None
        """
        self.exposure.confirm_print_start()

    @auto_dbus
    @state_checked(Exposure0State.POUR_IN_RESIN)
    def confirm_resin_in(self) -> None:
        """
        Confirm resin poured in

        :return: None
        """
        self.exposure.confirm_resin_in()

    @auto_dbus
    @state_checked(Exposure0State.CHECK_WARNING)
    def confirm_print_warning(self) -> None:
        """
        Confirm print continue despite of warnings

        :return: None
        """
        self.exposure.confirm_print_warning()

    @auto_dbus
    @state_checked(Exposure0State.CHECK_WARNING)
    def reject_print_warning(self) -> None:
        """
        Escalate warning to error and cancel print

        :return: None
        """
        self.exposure.reject_print_warning()

    @auto_dbus
    @property
    def exposure_warning(self) -> Dict[str, Any]:
        """
        Get current exposure warning.

        .. seealso:: :meth:`slafw.errors.codes.WarningCode`

        Each exposure warning is represented as dictionary str -> variant::

            {
                "code": code
                "code_specific_feature1": value1
                "code_specific_feature2": value2
            }

        :return: Warning dictionary
        """
        return wrap_dict_data(PrinterWarning.as_dict(self.exposure.data.warning))

    @auto_dbus
    @property
    def checks_state(self) -> Dict[int, int]:
        """
        State of exposure checks

        :return: Dictionary mapping from check id to state id
        """
        if not self.exposure.data.check_results:
            return {}

        return {check.value: state.value for check, state in self.exposure.data.check_results.items()}

    @auto_dbus
    @property
    def current_layer(self) -> int:
        """
        Layer currently being printed

        :return: Layer number
        """
        return self.exposure.data.actual_layer

    @auto_dbus
    @property
    def current_area_fill(self) -> int:
        """
        Layer currently being printed

        :return: Layer number
        """
        return self.exposure.data.current_area_fill

    @auto_dbus
    @property
    def total_layers(self) -> int:
        """
        Total number of layers in the project

        :return:
        """
        return self.exposure.project.total_layers

    @auto_dbus
    @property
    def time_remain_ms(self) -> int:
        """
        Remaining print time

        :return: Remaining time in minutes
        """
        if self.exposure.data.estimated_total_time_ms > 2**31-1:
            self._logger.error("Time remain out of int32 range: %d ms, capping to max value",
                              self.exposure.data.estimated_total_time_ms)
            return 2**31-1
        return self.exposure.estimate_remain_time_ms()

    @auto_dbus
    @property
    def total_time_ms(self) -> int:
        """
        Estimated total print time in ms
        """
        if self.exposure.data.estimated_total_time_ms > 2**31-1:
            self._logger.error("Estimated total time out of int32 range: %d ms, capping to max value",
                              self.exposure.data.estimated_total_time_ms)
            return 2**31-1
        return self.exposure.data.estimated_total_time_ms

    @auto_dbus
    @property
    def expected_finish_timestamp(self) -> float:
        """
        Get timestamp of expected print end

        :return: Timestamp as float
        """
        return self.exposure.expected_finish_timestamp()

    @auto_dbus
    @property
    def print_start_timestamp(self) -> float:
        """
        Get print start timestamp

        :return: Timestamp
        """
        return self.exposure.data.print_start_time.timestamp()

    @auto_dbus
    @property
    def print_end_timestamp(self) -> float:
        """
        Get print end timestamp

        :return: Timestamp
        """
        return self.exposure.data.print_end_time.timestamp()

    @auto_dbus
    @property
    def layer_height_first_nm(self) -> int:
        """
        Height of the first layer

        :return: Height in nanometers
        """
        return self.exposure.project.layer_height_first_nm

    @auto_dbus
    @property
    def layer_height_nm(self) -> int:
        """
        Height of the standard layer

        :return: Height in nanometers
        """
        return self.exposure.project.layer_height_nm

    @auto_dbus
    @property
    def position_nm(self) -> int:
        """
        Current layer position

        :return: Layer position in nanometers
        """
        return int(self.exposure.hw.tower.position)

    @auto_dbus
    @property
    def total_nm(self) -> int:
        """
        Model height

        :return: Height in nanometers
        """
        return self.exposure.project.total_height_nm

    @auto_dbus
    @property
    def project_name(self) -> str:
        """
        Name of the project

        :return: Name as string
        """
        return self.exposure.project.name

    @auto_dbus
    @property
    def project_file(self) -> str:
        """
        Full path to the project being printed

        :return: Project file with path
        """
        return str(self.exposure.project.data.path)

    @auto_dbus
    @property
    def progress(self) -> float:
        """
        Progress percentage

        :return: Percentage 0 - 100
        """
        # TODO: In new API revision report progress as 0-1
        return 100 * self.exposure.progress

    @auto_dbus
    @property
    def resin_used_ml(self) -> float:
        """
        Amount of resin used

        :return: Volume in milliliters
        """
        return self.exposure.data.resin_count_ml

    @auto_dbus
    @property
    def resin_remaining_ml(self) -> float:
        """
        Remaining resin in the tank

        :return: Volume in milliliters
        """
        if self.exposure.data.resin_remain_ml:
            return self.exposure.data.resin_remain_ml
        return -1

    @auto_dbus
    @property
    def resin_measured_ml(self) -> float:
        """
        Amount of resin measured during last measurement

        :return: Resin volume in milliliters, or -1 if not measured yet
        """
        if self.exposure.resin_volume:
            return self.exposure.resin_volume
        return -1

    @auto_dbus
    @property
    def total_resin_required_ml(self) -> float:
        """
        Total resin required to finish the project

        This is project used material plus minimal amount of resin required for the printer to work

        :return: Required resin in milliliters
        """
        return self.exposure.project.used_material_nl / 1e6 + defines.resinMinVolume

    @auto_dbus
    @property
    def total_resin_required_percent(self) -> float:
        """
        Total resin required to finish the project

        Values over 100 mean the tank has to be refilled during the print.

        :return: Required resin in tank percents
        """
        return self.exposure.hw.calcPercVolume(self.exposure.project.used_material_nl / 1e6 + defines.resinMinVolume)

    @auto_dbus
    @property
    def resin_warn(self) -> bool:
        """
        Whenever the remaining resin has reached warning level

        :return: True if reached, False otherwise
        """
        return self.exposure.data.resin_warn

    @auto_dbus
    @property
    def resin_low(self) -> bool:
        """
        Whenever the resin has reached forced pause level

        :return: True if reached, False otherwise
        """
        return self.exposure.data.resin_low

    @auto_dbus
    @property
    def remaining_wait_sec(self) -> int:
        """
        If in waiting state this is number of seconds remaing in wait

        :return: Number of seconds
        """
        return self.exposure.data.remaining_wait_sec

    @auto_dbus
    @property
    def wait_until_timestamp(self) -> float:
        """
        If in wait state this represents end of wait timestamp

        :return: Timestamp as float
        """
        return (datetime.now(tz=timezone.utc) + timedelta(seconds=self.exposure.data.remaining_wait_sec)).timestamp()

    @auto_dbus
    @property
    def exposure_end(self) -> float:
        """
        End of current layer exposure

        :return: Timestamp as float, or -1 of no layer exposed to UV
        """
        if self.exposure.data.exposure_end:
            return self.exposure.data.exposure_end.timestamp()
        return -1

    @auto_dbus
    @property
    def state(self) -> int:
        """
        Print job state :class:`.states.Exposure0State`

        :return: State as integer
        """
        return Exposure0State.from_exposure(self.exposure.data.state).value

    @auto_dbus
    @property
    def close_cover_warning(self) -> bool:
        return self.exposure.hw.config.coverCheck and not self.exposure.hw.isCoverClosed(False)

    @auto_dbus
    @state_checked(Exposure0State.PRINTING)
    def up_and_down(self) -> None:
        """
        Do up and down

        :return: None
        """
        self.exposure.doUpAndDown()

    @auto_dbus
    @state_checked(
        [
            Exposure0State.PRINTING,
            Exposure0State.CHECKS,
            Exposure0State.CONFIRM,
            Exposure0State.COVER_OPEN,
            Exposure0State.POUR_IN_RESIN,
            Exposure0State.HOMING_AXIS,
        ]
    )
    def cancel(self) -> None:
        """
        Cancel print

        :return: None
        """
        self.exposure.cancel()

    @auto_dbus
    @state_checked([
        Exposure0State.FINISHED,
        Exposure0State.CANCELED,
        Exposure0State.FAILURE,
        Exposure0State.DONE
    ])
    def stats_seen(self) -> None:
        """
        Mark completed exposure as seen by user. This is supposed to be called after user has dismissed after
        print stats.

        :return: None
        """
        self.exposure.stats_seen()

    @auto_dbus
    @state_checked(Exposure0State.PRINTING)
    def feed_me(self) -> None:
        """
        Start manual feedme

        :return: None
        """
        self.exposure.doFeedMe()

    @auto_dbus
    @state_checked([Exposure0State.FEED_ME, Exposure0State.STUCK])
    def cont(self) -> None:
        """
        Continue print after pause or feedme

        :return: None
        """
        self.exposure.doContinue()

    @auto_dbus
    @state_checked([Exposure0State.FEED_ME, Exposure0State.STUCK])
    def back(self) -> None:
        """
        Do legacy back

        Useful to back manual feedme

        :return: None
        """
        self.exposure.doBack()

    @property
    def exposure_time_ms(self) -> int:
        return self.exposure.project.exposure_time_ms

    @auto_dbus
    @range_checked(defines.exposure_time_min_ms, defines.exposure_time_max_ms)
    @exposure_time_ms.setter
    def exposure_time_ms(self, value: int) -> None:
        self.exposure.project.exposure_time_ms = value

    @auto_dbus
    def user_profile_get(self, below: bool) -> LayerProfileTuple:
        """
        Get exposure profile for below or above area fill

        :return: Tuple with exposure profile data
        """
        if below:
            return tuple(self.exposure.project.exposure_profile.below_area_fill.dump())  # type: ignore[return-value]
        return tuple(self.exposure.project.exposure_profile.above_area_fill.dump())  # type: ignore[return-value]

    @auto_dbus
    def user_profile_set(self, below: bool, data: LayerProfileTuple) -> None:
        self.exposure.project.exposure_profile_set(below, data)

    @auto_dbus
    @property
    def area_fill(self) -> int:
        """
        Percentage of area of current layer
        Printer selects below or above profiles based on this value.

        :return: Area fill percentage
        """
        return self.exposure.project.exposure_profile.area_fill

    @auto_dbus
    @range_checked(0, 100)
    @area_fill.setter
    def area_fill(self, value: int) -> None:
        self.exposure.project.exposure_profile.area_fill = value
        self.PropertiesChanged(self.__INTERFACE__, {"area_fill": self.area_fill}, [])

    @property
    def exposure_time_first_ms(self) -> int:
        return self.exposure.project.exposure_time_first_ms

    @auto_dbus
    @range_checked(defines.exposure_time_min_ms, defines.exposure_time_first_max_ms)
    @exposure_time_first_ms.setter
    def exposure_time_first_ms(self, value: int) -> None:
        self.exposure.project.exposure_time_first_ms = value

    @property
    def exposure_time_calibrate_ms(self) -> int:
        return self.exposure.project.calibrate_time_ms

    @auto_dbus
    @range_checked(defines.exposure_time_min_ms, defines.exposure_time_calibrate_max_ms)
    @exposure_time_calibrate_ms.setter
    def exposure_time_calibrate_ms(self, value: int) -> None:
        self.exposure.project.calibrate_time_ms = value

    @auto_dbus
    @property
    def calibration_regions(self) -> int:
        """
        Number of calibration regions

        Zero regions means the project is not calibration project.

        :return: Number of calibration regions
        """
        return self.exposure.project.calibrate_regions

    @auto_dbus
    def inject_fatal_error(self):
        self.exposure.inject_fatal_error()

    @auto_dbus
    def inject_exception(self, code: str):
        self.exposure.inject_exception(code)

    _CHANGE_MAP = {
        # exposure
        "state": {"state"},
        "actual_layer": {
            "current_layer",
            "progress",
            "time_remain_ms",
            "position_nm",
            "expected_finish_timestamp",
            "current_area_fill",
        },
        "resin_count_ml": {"resin_used_ml"},
        "resin_remain_ml": {"resin_remaining_ml"},
        "resin_warn": {"resin_warn"},
        "resin_low": {"resin_low"},
        "remaining_wait_sec": {"remaining_wait_sec"},
        "estimated_total_time_ms": {"total_time_ms"},
        "print_start_time": {"print_start_timestamp"},
        "print_end_time": {"print_end_timestamp"},
        "exposure_end": {"exposure_end"},
        "check_results": {"checks_state"},
        "warning": {"exposure_warning"},
        "fatal_error": {"failure_reason"},
        # project
        "path": {"project_file"},
        "exposure_time_ms": {"exposure_time_ms"},
        "exposure_time_first_ms": {"exposure_time_first_ms"},
        "calibrate_time_ms": {"exposure_time_calibrate_ms"},
        "calibrate_regions": {"calibration_regions"},
        "exposure_profile_id": {"user_profile"},
    }

    _SIGNAL_MAP = {
        "exception": {"error": "exception_occurred"},
    }

    def _handle_exposure_change(self, key: str, value: Any):
        self._logger.debug("handle_exposure_change: %s set to %s", key, value)
        if key in self._CHANGE_MAP:
            content = {}
            for changed in self._CHANGE_MAP[key]:
                content[changed] = getattr(self, changed)
            self._logger.debug("PropertiesChanged: %s", content)
            self.PropertiesChanged(self.__INTERFACE__, content, [])
        if key in self._SIGNAL_MAP:
            for signal_name, get_change in self._SIGNAL_MAP[key].items():
                getattr(self, signal_name)(getattr(self, get_change))

    def _handle_cover_change(self):
        self.PropertiesChanged(self.__INTERFACE__, {"close_cover_warning": self.close_cover_warning}, [])

    def _handle_config_change(self, name: str, _: Any):
        if name == "coverCheck":
            self._handle_cover_change()

    def _handle_cover_change_param(self, _):
        self._handle_cover_change()
