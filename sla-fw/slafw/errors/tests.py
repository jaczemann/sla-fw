# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2020 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from re import findall
from typing import Collection, Tuple, Any
from dataclasses import make_dataclass

from prusaerrors.sl1.codes import Sl1Codes


from slafw.errors import warnings
from slafw.errors.errors import with_code, PrinterException
from slafw.motion_controller.trace import Trace
from slafw.states.printer import PrinterState

FAKE_ARGS = {
    "url": "http://example.com",
    "total_bytes": 0,
    "completed_bytes": 0,
    "failed_fans": [1],
    "failed_fan_names": "UV Fan",
    "volume": 12.3,
    "volume_ml": 12.3,
    "failed_sensors": [2],
    "failed_sensor_names": ["UV LED temperature"],
    "trace": Trace(10),
    "current_state": PrinterState.PRINTING,
    "allowed_states": [PrinterState.PRINTING],
    "ambient_temperature": 42,
    "actual_model": "Some other printer",
    "actual_variant": "Some other variant",
    "printer_variant": "default",
    "project_variant": "something_else",
    "changes": { "exposure": (10, 20)},
    "measured_resin_ml": 12.3,
    "required_resin_ml": 23.4,
    "warning": warnings.AmbientTooHot(ambient_temperature=42.0),  # type: ignore
    "name": "fan1",
    "fan": "fan1",
    "rpm": 1234,
    "fanError": {0: False, 1: True, 2: False},
    "uv_temp_deg_c": 42.42,
    "position": 12345,
    "position_mm": 48.128,
    "position_nm": 48128,
    "avg": 10,
    "a64": 1,
    "mc": 1,
    "tilt_position": 5000,
    "tower_position_nm": 100000000,
    "sn": "123456789",
    "min_resin_ml": 10,
    "failed_fans_text": "UV LED Fan",
    "fans": ["UV LED Fan"],
    "found": 240,
    "allowed": 250,
    "intensity": 150,
    "threshold": 125,
    "nonprusa_code": 42,
    "temperature": 36.8,
    "sensor": "Ambient temperature",
    "message": "Exception message string",
    "reason": "Everything is broken",
    "pwm": 142,
    "pwm_min": 150,
    "pwm_max": 250,
    "transmittance": -1,
    "counter_h": 500,
    "fan__map_HardwareDeviceId": 2000,
    "sensor__map_HardwareDeviceId": 1000,
    "min": 5.0,
    "max": 55.0,
    "min_rpm": 1000,
    "max_rpm": 5000,
    "avg_rpm": 500,
    "lower_bound_rpm": 1200,
    "upper_bound_rpm": 1800,
    "error": 1,
    "temperature: float": 0,
}

IGNORED_ARGS = {"self", "args", "kwargs"}


def get_classes() -> Collection[Tuple[str, Exception]]:
    error_codes = Sl1Codes.get_codes()

    for code_id in error_codes:
        class_name = f"{code_id.title().replace('_', '')}"
        new_class = with_code(getattr(Sl1Codes, code_id)) (type(class_name, (PrinterException,), {}))

        if not isinstance(new_class, type):
            continue

        if not issubclass(new_class, Exception):
            continue

        yield class_name, new_class


def get_instance(cls):
    params = findall(r'%\((.*?)\)', cls.MESSAGE)
    args = [FAKE_ARGS[str(param)] for param in params]

    if not params or not args:
        return cls(*args)

    fields = [(param, Any) for param in params]
    temp = make_dataclass(cls.__name__, fields, bases=(cls,))

    return temp(*args)


def get_instance_by_code(code: str):
    for _, cls in get_classes():
        if getattr(cls, "CODE", None).code == code:
            return get_instance(cls)
    raise ValueError(f"Unknown exception code to inject {code}")
