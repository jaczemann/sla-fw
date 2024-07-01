# This file is part of the SLA firmware
# Copyright (C) 2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import datetime, timedelta

from PySignal import Signal

from slafw.states.exposure import ExposureState, ExposureCheck, ExposureCheckResult
from slafw.exposure.exposure import ExposureData
from slafw.hardware.printer_model import PrinterModel
from slafw.tests.mocks.hardware import HardwareMock
from slafw.tests.mocks.project import Project



class Exposure:
    def __init__(self):
        exposure_end = datetime.utcnow() + timedelta(hours=10)
        self.data = ExposureData(
                changed = Signal(),
                instance_id = 1,
                state = ExposureState.PRINTING,
                actual_layer = 42,
                resin_count_ml = 4,
                resin_remain_ml = 142,
                resin_warn = False,
                resin_low = False,
                remaining_wait_sec = 4242,
                estimated_total_time_ms = 123456,
                print_start_time = datetime.utcnow(),
                print_end_time = exposure_end,
                exposure_end = exposure_end,
                check_results = {
                    ExposureCheck.FAN: ExposureCheckResult.RUNNING,
                    ExposureCheck.PROJECT: ExposureCheckResult.RUNNING,
                    ExposureCheck.RESIN: ExposureCheckResult.SCHEDULED,
                    ExposureCheck.COVER: ExposureCheckResult.DISABLED,
                    ExposureCheck.START_POSITIONS: ExposureCheckResult.SUCCESS,
                },
                warning = None,
        )
        self.hw = HardwareMock(printer_model=PrinterModel.SL1)
        self.project = Project()
        self.progress = 0
        self.resin_volume = 42
        self.tower_position_nm = 424242
        self.warning_occurred = Signal()

    def expected_finish_timestamp(self):
        return datetime.utcnow() + timedelta(milliseconds=self.estimate_remain_time_ms())

    def estimate_remain_time_ms(self):
        return self.project.data.exposure_time_ms * (self.project.total_layers - self.data.actual_layer)

    def set_state(self, state):
        self.data.state = state
        self.data.changed.emit("state", state)
        self.data.changed.emit("check_results", self.data.check_results)
