# This file is part of the SLA firmware
# Copyright (C) 2020-2024 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
from collections import deque
from dataclasses import dataclass
from typing import Optional, Callable, Deque

from PySignal import Signal

from slafw.hardware.hardware import BaseHardware
from slafw.states.wizard import WizardState

@dataclass
class PushState:
    state: WizardState


class UserAction:
    def __init__(self):
        self.callback: Optional[Callable] = None

    def __call__(self, *args, **kwargs):
        if not self.callback:
            raise KeyError("User action not registered")
        self.callback(*args, **kwargs)

    def register_callback(self, callback: Callable):
        if self.callback:
            raise ValueError("Callback already registered")
        self.callback = callback

    def unregister_callback(self):
        self.callback = None


class UserActionBroker:
    # pylint: disable=too-many-instance-attributes
    def __init__(self, hw: BaseHardware):
        self._logger = logging.getLogger(__name__)
        self._states: Deque[PushState] = deque()
        self.states_changed = Signal()
        self._hw = hw

        self.prepare_calibration_platform_align_done = UserAction()
        self.prepare_calibration_tilt_align_done = UserAction()
        self.prepare_calibration_finish_done = UserAction()

        self.prepare_displaytest_done = UserAction()
        self.prepare_calibration_platform_tank_done = UserAction()

        self.report_display = UserAction()
        self.report_audio = UserAction()
        self.tilt_move = UserAction()
        self.tilt_aligned = UserAction()
        self.show_results_done = UserAction()

        # Unboxing
        self.safety_sticker_removed = UserAction()
        self.side_foam_removed = UserAction()
        self.tank_foam_removed = UserAction()
        self.display_foil_removed = UserAction()

        # Self-test
        self.prepare_wizard_part_1_done = UserAction()
        self.prepare_wizard_part_2_done = UserAction()
        self.prepare_wizard_part_3_done = UserAction()

        # Packing
        self.foam_inserted = UserAction()

        # UV Calibration
        self.uv_calibration_prepared = UserAction()
        self.uv_meter_placed = UserAction()
        self.uv_apply_result = UserAction()
        self.uv_discard_results = UserAction()

        # SL1S upgrade
        self.sl1s_confirm_upgrade = UserAction()
        self.sl1s_reject_upgrade = UserAction()

        # New exposure panel
        self.new_expo_panel_done = UserAction()

        # Tank Surface Cleaner
        self.tank_surface_cleaner_init_done = UserAction()
        self.insert_cleaning_adaptor_done = UserAction()
        self.remove_cleaning_adaptor_done = UserAction()

    def push_state(self, state: PushState, priority: bool = False):
        if priority:
            self._states.appendleft(state)
        else:
            self._states.append(state)
        self._logger.debug("Pushing wizard state: %s", state)
        self.states_changed.emit()

    def drop_state(self, state: PushState):
        self._states.remove(state)
        self._logger.debug("Removing wizard state: %s", state)
        self.states_changed.emit()

    @property
    def led_warn(self):
        return self._hw.power_led
