#!/bin/bash

# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

HEX="$1/SLA-control_rev06.hex"
PORT=$2
avrdude -p ATmega32u4 -P "$PORT" -c avr109 -F -v -u -V -U "flash:w:$HEX:i"
