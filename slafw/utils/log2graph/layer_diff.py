#!/usr/bin/python

# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import sys

last = -1.0

for line in sys.stdin:
    items = line.strip().split(" ")
    timeparts = items[0].split(":")
    seconds = int(timeparts[0]) * 3600 + int(timeparts[1]) * 60 + float(timeparts[2])
    if seconds < last:
        seconds += 24 * 3600
    if last < 0:
        last = seconds
        continue
    print(seconds - last, items[1], items[2], items[3], items[4])
    last = seconds
