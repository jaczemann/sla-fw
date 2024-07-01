#!/usr/bin/env python2

# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
from time import sleep
from typing import List

from slafw.configs.hw import HwConfig
from slafw.hardware.sl1.hardware import HardwareSL1
from slafw.hardware.printer_model import PrinterModel

logging.basicConfig(format = "%(asctime)s - %(levelname)s - %(name)s - %(message)s", level = logging.DEBUG)

printer_model = PrinterModel.SL1
hw_config = HwConfig()
hw = HardwareSL1(hw_config, printer_model)

hw.tilt.sync_ensure()
hw.tilt.move(5300)
while hw.tilt.moving:
    sleep(0.1)
#endwhile
profile = [1750, 1750, 0, 0, 58, 26, 2100]
result = {}
for sgt in range(10, 30):
    profile[5] = sgt
    sgbd: List[int] = []
    hw.mcc.do("!tics", 4)
    hw.mcc.do("!ticf", ' '.join(str(num) for num in profile))
    hw.mcc.do("?ticf")
    hw.mcc.do("!sgbd")
    hw.tilt.move(0)
    while hw.tilt.moving:
        sgbd.extend(hw.getStallguardBuffer())
        sleep(0.1)
    #endwhile
    if hw.tilt.position == 0:
        avg = sum(sgbd) / float(len(sgbd))
        if 200 < avg < 250:
            result[avg] = ' '.join(str(num) for num in profile)

    hw.mcc.do("!tics", 0)
    hw.tilt.move(5300)
    while hw.tilt.moving:
        sleep(0.1)
    #endwhile

print(result)
hw.mcc.do("!motr")
