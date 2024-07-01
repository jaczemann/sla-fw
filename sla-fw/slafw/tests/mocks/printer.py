# This file is part of the SLA firmware
# Copyright (C) 2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from PySignal import Signal

from slafw.configs.runtime import RuntimeConfig
from slafw.states.printer import PrinterState
from slafw.tests.mocks.network import Network


class Printer:
    # pylint: disable = too-many-instance-attributes
    def __init__(self, hw, action_manager):
        self.state_changed = Signal()
        self.http_digest_password_changed = Signal()
        self.data_privacy_changed = Signal()
        self.exception_changed = Signal()
        self.hw = hw
        self.action_manager = action_manager
        self.runtime_config = RuntimeConfig()
        self.unboxed_changed = Signal()
        self.self_tested_changed = Signal()
        self.mechanically_calibrated_changed = Signal()
        self.uv_calibrated_changed = Signal()
        self.inet = Network()
        self.exception_occurred = Signal()
        self.fatal_error_changed = Signal()

        self.state = PrinterState.PRINTING
        self.exception = None

        self.http_digest_password = "developer"
        self.data_privacy = "data privacy"
        self.help_page_url = "hpu"
        self.unboxed = True
        self.self_tested = True
        self.uv_calibrated = True
        self.mechanically_calibrated = True

    def remove_oneclick_inhibitor(self, _):
        pass

    def set_state(self, state):
        self.state = state
        self.state_changed.emit()
