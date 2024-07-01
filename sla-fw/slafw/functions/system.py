# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2020 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import os
import subprocess
from math import isclose

import pydbus

from slafw import defines, test_runtime
from slafw.configs.hw import HwConfig
from slafw.errors.errors import (
    FailedUpdateChannelSet,
    FailedUpdateChannelGet,
    PrinterException,
    DisplayTransmittanceNotValid,
    CalculatedUVPWMNotInRange
)
from slafw.hardware.hardware import BaseHardware
from slafw.hardware.printer_model import PrinterModel


set_update_channel_bin = "/usr/sbin/set-update-channel.sh"


def shut_down(hw: BaseHardware, reboot=False):
    hw.uv_led.off()
    hw.motors_release()
    if reboot:
        os.system("reboot")
    else:
        os.system("poweroff")


def get_update_channel() -> str:
    try:
        return defines.update_channel.read_text(encoding="ascii").strip()
    except (FileNotFoundError, PermissionError) as e:
        raise FailedUpdateChannelGet() from e


def set_update_channel(channel: str):
    try:
        subprocess.check_call([set_update_channel_bin, channel])
    except Exception as e:
        raise FailedUpdateChannelSet() from e


class FactoryMountedRW:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def __enter__(self):
        self.logger.info("Remounting factory partition rw")
        if test_runtime.testing:
            self.logger.warning("Skipping factory RW remount due to testing")
        else:
            subprocess.check_call(["/usr/bin/mount", "-o", "remount,rw", str(defines.factoryMountPoint)])

    def __exit__(self, exception_type, exception_value, exception_traceback):
        self.logger.info("Remounting factory partition ro")
        if test_runtime.testing:
            self.logger.warning("Skipping factory RW remount due to testing")
        else:
            subprocess.check_call(["/usr/bin/mount", "-o", "remount,ro", str(defines.factoryMountPoint)])


def set_configured_printer_model(model: PrinterModel):
    """
    Adjust printer model definition files to match new printer model

    :param model: New printer model
    """

    # Clear existing model definitions
    for file in defines.printer_model.glob("*"):
        if file.is_file():
            file.unlink()

    # Add new model definition
    model_file = defines.printer_model / model.name.lower()  # type: ignore[attr-defined]
    model_file.parent.mkdir(exist_ok=True)
    model_file.touch()


def get_configured_printer_model() -> PrinterModel:
    for model in PrinterModel:
        model_file = defines.printer_model / model.name.lower()
        if model_file.exists():
            return model
    return PrinterModel.NONE


# TODO: move into hw.uv_led
def set_factory_uvpwm(pwm: int) -> None:
    """
    This is supposed to read current factory config, set the new uvPWM and save factory config
    """
    config = HwConfig(file_path=defines.hwConfigPath, factory_file_path=defines.hwConfigPathFactory, is_master=True)
    config.read_file()
    config.uvPwm = pwm
    with FactoryMountedRW():
        config.write_factory()


def compute_uvpwm(hw: BaseHardware) -> int:
    trans = hw.exposure_screen.transmittance
    if isclose(trans, 0.0, abs_tol=0.001):
        raise DisplayTransmittanceNotValid(trans)

    pwm = int(-35 * trans + 350)

    pwm_min = hw.uv_led.parameters.min_pwm
    pwm_max = hw.uv_led.parameters.max_pwm
    if not pwm_min < pwm < pwm_max:
        raise CalculatedUVPWMNotInRange(pwm, pwm_min, pwm_max)

    return pwm


def get_hostname() -> str:
    return pydbus.SystemBus().get("org.freedesktop.hostname1").StaticHostname


def set_hostname(hostname: str) -> None:
    try:
        dbus = pydbus.SystemBus().get("org.freedesktop.hostname1")
        dbus.SetStaticHostname(hostname, False)
        dbus.SetHostname(hostname, False)
    except Exception as exception:
        raise PrinterException("Cannot set hostname") from exception


def reset_hostname() -> None:
    printer_model = get_configured_printer_model()
    set_hostname(defines.default_hostname + printer_model.name.lower())  # type: ignore[attr-defined]

def printer_model_regex(upper_case: bool = False) -> str:
    """
    upper_case: Names are in upper case if True. Default is False -> lowercase
    returns regexp group matching one of the printer model names except for NONE. Ex.: (sl1|sl1s|m1)
    """
    model_string = "("
    for model in PrinterModel:
        if model is not PrinterModel.NONE:
            if upper_case:
                model_string += model.name + "|"
            else:
                model_string += model.name.lower() + "|"
    return model_string[:-1] + ")"
