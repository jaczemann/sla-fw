#!/usr/bin/env python

# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2020-2022 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import warnings

from gi.repository import GLib
from pydbus import SystemBus

from slafw import libPrinter
from slafw import defines
from slafw import __full_version__
from slafw.api.admin0 import Admin0
from slafw.api.printer0 import Printer0
from slafw.api.standard0 import Standard0
from slafw.admin.manager import AdminManager
from slafw.logger_config import configure_log

log_from_config = configure_log(name=defines.component_name)
logger = logging.getLogger()

if log_from_config:
    logger.info("Logging configuration read from configuration file")
else:
    logger.info("Embedded logger configuration was used")

logger.info("Logging is set to level %s", logging.getLevelName(logger.level))
logger.info("Version: %s", __full_version__)

warnings.simplefilter("ignore")

printer = libPrinter.Printer()
printer0 = Printer0(printer)

SystemBus().publish(Printer0.__INTERFACE__, printer0)
SystemBus().publish(Standard0.__INTERFACE__, Standard0(printer))
admin_manager = AdminManager()
SystemBus().publish(Admin0.__INTERFACE__, Admin0(admin_manager, printer))
printer.setup()
# Register HW dependent event in case we actually have the hardware
# If not, it should be registered at later time
if printer.hw:
    printer0.register_hardware(printer.hw)
printer.run_make_ready_to_print()

logger.info("Running DBus event loop")
GLib.MainLoop().run()  # type: ignore[attr-defined]
