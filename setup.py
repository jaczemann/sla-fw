# This file is part of the SLA firmware
# Copyright (C) 2023 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from os import system
from setuptools import setup

if __name__ == '__main__':
    system("./make_version.sh")
    setup()
