# This file is part of the SLA firmware
# Copyright (C) 2020 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Any, Dict, List

from pydbus.generic import signal

from slafw.api.decorators import (
    dbus_api,
    auto_dbus,
    wrap_dict_data,
    wrap_dict_data_recursive,
)
from slafw.errors.errors import PrinterException
from slafw.errors.warnings import PrinterWarning
from slafw.wizard.wizard import Wizard


@dbus_api
class Wizard0:
    """
    Wizard0 DBus API

    This object is an abstract representation of any wizard. The identifier property distinguishes which wizard
    is being run.

    Based on wizard state and wizard type set of actions can be performed. Actions invalid for current wizard in
    current state raise an exception.

    A wizard consists of checks. The checks can be inspected sing check_data and check_states properties.

    # Error handling
    Errors and exception come with data dictionary that is supposed to include at last a "code" member pointing to a
    standard Prusa error code.

    - Errors resulting from DBus calls are reported as native DBus errors. Exception data dictionary is embedded as json
      into a DBus error message.
    - Fatal error that crashed the internal thread (failed the wizard) is stored in check_exception
      property including data dictionary.
    - Non-Fatal errors/warnings are store in check_warnings property as a list.
    """

    # pylint: disable = too-many-public-methods
    __INTERFACE__ = "cz.prusa3d.sl1.wizard0"
    DBUS_PATH = "/cz/prusa3d/sl1/wizard0"
    PropertiesChanged = signal()

    def __init__(self, wizard: Wizard):
        self._wizard = wizard

        wizard.started_changed.connect(self._started_changed)
        wizard.state_changed.connect(self._state_changed)
        wizard.check_states_changed.connect(self._check_states_changed)
        wizard.exception_changed.connect(self._exception_changed)
        wizard.warnings_changed.connect(self._warnings_changed)
        wizard.check_data_changed.connect(self._check_data_changed)
        wizard.data_changed.connect(self._data_changed)

    @auto_dbus
    @property
    def identifier(self) -> int:
        return self._wizard.identifier.value

    @auto_dbus
    @property
    def state(self) -> int:
        return self._wizard.state.value

    @auto_dbus
    @property
    def check_states(self) -> Dict[int, int]:
        return {check.value: state.value for check, state in self._wizard.check_state.items()}

    @auto_dbus
    @property
    def check_data(self) -> Dict[int, Dict[str, Any]]:
        return {check.value: wrap_dict_data_recursive(data) for check, data in self._wizard.check_data.items()}

    @auto_dbus
    @property
    def check_exception(self) -> Dict[str, Any]:
        return wrap_dict_data(PrinterException.as_dict(self._wizard.exception))

    @auto_dbus
    @property
    def check_warnings(self) -> List[Dict[str, Any]]:
        """
        Get current list of warnings.

        Each exposure warning is represented as dictionary str -> Variant::

            {
                "code": code
                "code_specific_feature1": value1
                "code_specific_feature2": value2
            }

        :return: List of warning dictionaries
        """
        return [wrap_dict_data(PrinterWarning.as_dict(warning)) for warning in self._wizard.warnings]

    @auto_dbus
    @property
    def data(self) -> Dict[str, Any]:
        return wrap_dict_data(self._wizard.data)

    @auto_dbus
    @property
    def cancelable(self) -> bool:
        return self._wizard.cancelable

    @auto_dbus
    def cancel(self):
        self._wizard.cancel()

    @auto_dbus
    def retry(self):
        self._wizard.retry()

    @auto_dbus
    def abort(self):
        self._wizard.abort()

    @auto_dbus
    def prepare_wizard_part_1_done(self):
        self._wizard.prepare_wizard_part_1_done()

    @auto_dbus
    def prepare_wizard_part_2_done(self):
        self._wizard.prepare_wizard_part_2_done()

    @auto_dbus
    def prepare_wizard_part_3_done(self):
        self._wizard.prepare_wizard_part_3_done()

    @auto_dbus
    def prepare_calibration_platform_tank_done(self):
        self._wizard.prepare_calibration_platform_tank_done()

    @auto_dbus
    def prepare_calibration_platform_align_done(self):
        self._wizard.prepare_calibration_platform_align_done()

    @auto_dbus
    def prepare_calibration_tilt_align_done(self):
        self._wizard.prepare_calibration_tilt_align_done()

    @auto_dbus
    def prepare_calibration_finish_done(self):
        self._wizard.prepare_calibration_finish_done()

    @auto_dbus
    def show_results_done(self):
        self._wizard.show_results_done()

    @auto_dbus
    def prepare_displaytest_done(self):
        self._wizard.prepare_displaytest_done()

    @auto_dbus
    def report_display(self, result: bool):
        self._wizard.report_display(result)

    @auto_dbus
    def report_audio(self, result: bool):
        self._wizard.report_audio(result)

    @auto_dbus
    def tilt_move(self, direction: int):
        self._wizard.tilt_move(direction)

    @auto_dbus
    def tilt_calibration_done(self):
        self._wizard.tilt_aligned()

    @auto_dbus
    def safety_sticker_removed(self):
        self._wizard.safety_sticker_removed()

    @auto_dbus
    def side_foam_removed(self):
        self._wizard.side_foam_removed()

    @auto_dbus
    def tank_foam_removed(self):
        self._wizard.tank_foam_removed()

    @auto_dbus
    def display_foil_removed(self):
        self._wizard.display_foil_removed()

    @auto_dbus
    def foam_inserted(self):
        self._wizard.foam_inserted()

    @auto_dbus
    def uv_calibration_prepared(self):
        self._wizard.uv_calibration_prepared()

    @auto_dbus
    def uv_meter_placed(self):
        self._wizard.uv_meter_placed()

    @auto_dbus
    def uv_apply_result(self):
        self._wizard.uv_apply_result()

    @auto_dbus
    def uv_discard_results(self):
        self._wizard.uv_discard_results()

    @auto_dbus
    def sl1s_confirm_upgrade(self):
        self._wizard.sl1s_confirm_upgrade()

    @auto_dbus
    def sl1s_reject_upgrade(self):
        self._wizard.sl1s_reject_upgrade()

    @auto_dbus
    def new_expo_panel_done(self):
        self._wizard.new_expo_panel_done()

    @auto_dbus
    def tank_surface_cleaner_init_done(self):
        self._wizard.tank_surface_cleaner_init_done()

    @auto_dbus
    def insert_cleaning_adaptor_done(self):
        self._wizard.insert_cleaning_adaptor_done()

    @auto_dbus
    def remove_cleaning_adaptor_done(self):
        self._wizard.remove_cleaning_adaptor_done()

    def _started_changed(self):
        self.PropertiesChanged(self.__INTERFACE__, {"identifier": self.identifier}, [])
        self.PropertiesChanged(self.__INTERFACE__, {"cancelable": self.cancelable}, [])

    def _state_changed(self, _):
        self.PropertiesChanged(self.__INTERFACE__, {"state": self.state}, [])

    def _check_states_changed(self):
        self.PropertiesChanged(self.__INTERFACE__, {"check_states": self.check_states}, [])

    def _exception_changed(self):
        self.PropertiesChanged(self.__INTERFACE__, {"check_exception": self.check_exception}, [])

    def _warnings_changed(self):
        self.PropertiesChanged(self.__INTERFACE__, {"check_warnings": self.check_warnings}, [])

    def _check_data_changed(self):
        self.PropertiesChanged(self.__INTERFACE__, {"check_data": self.check_data}, [])

    def _data_changed(self):
        self.PropertiesChanged(self.__INTERFACE__, {"data": self.data}, [])
