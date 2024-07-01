#!/usr/bin/env bash

# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

if [ -n "${1}" ]; then
        VACUUM_TIME=$1
else
        exit 1
fi;

journalctl --rotate --vacuum-time=$VACUUM_TIME
