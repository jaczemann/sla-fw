#!/usr/bin/python3

# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import sys

from slafw.hardware.sl1.sl1s_uvled_booster import Booster

logging.basicConfig(format = "%(asctime)s - %(levelname)s - %(name)s - %(message)s", level = logging.DEBUG)

booster = Booster()
booster.connect()

booster.pwm = int(sys.argv[1])
logging.info("actual PWM = %d", booster.pwm)

#booster.eeprom_write_block(0, list(range(128)))
#booster.eeprom_write_block(0, list([0xFF] * 128))
booster.eeprom_write_block(2, list(range(18)))
#booster.eeprom_write_byte(127, 48)

data = booster.eeprom_read_block(0, 128)
logging.info("all %d bytes: %s", len(data), data)
logging.info("byte at 127: %d", booster.eeprom_read_byte(127))
