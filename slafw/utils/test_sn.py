#!/usr/bin/python2

# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import sys

import bitstring

# pylint: disable = unbalanced-tuple-unpacking
# pylint does not understand tuples passed by bitstring

if len(sys.argv) != 2:
    print(f"Usage: {sys.argv[0]} nvram_file")
    sys.exit(1)

with open(sys.argv[1], "rb") as file:
    s = bitstring.BitArray(bytes=file.read())

mac, mcs1, mcs2, snbe = s.unpack("pad:192, bits:48, uint:8, uint:8, pad:224, uintbe:64")

mcsc = mac.count(1)
if mcsc == mcs1 and mcsc ^ 255 == mcs2:
    print(f"MAC checksum OK ({mcs1:02x}:{mcs2:02x})")
    print(":".join([x.encode("hex") for x in mac.bytes]))
else:
    print(f"MAC checksum FAIL (is {mcs1:02x}:{mcs2:02x}, should be {mcsc:02x}:{mcsc ^ 255:02x})")


print()

# byte order change
sn = bitstring.BitArray(length=64, uintle=snbe)

ot = {0: "CZP"}

scs2, scs1, snnew = sn.unpack("uint:8, uint:8, bits:48")

scsc = snnew.count(1)
if scsc == scs1 and scsc ^ 255 == scs2:
    print(f"SN checksum OK ({scs1:02x}:{scs2:02x})")
    sequence_number, is_kit, ean_pn, year, week, origin = snnew.unpack(
        "pad:4, uint:17, bool, uint:10, uint:6, uint:6, uint:4"
    )
    txt = ""
else:
    print(f"SN checksum FAIL (is {scs1:02x}:{scs2:02x}, should be {scsc:02x}:{scsc ^ 255:02x})")
    sequence_number, is_kit, ean_pn, year, week, origin = sn.unpack(
        "pad:14, uint:17, bool, uint:10, uint:6, pad:2, uint:6, pad:2, uint:4"
    )
    txt = "*"

print(
    f"{txt}{ot.get(origin, 'UNK'):3s}X{week:02d}{year:02d}X{ean_pn:03d}X{'K' if is_kit else 'C':c}{sequence_number:05d}"
)
