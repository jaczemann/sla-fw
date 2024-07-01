#!/usr/bin/env bash

# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

if [ -n "${1}" ]; then
        LOG_PATH=$1
else
        LOG_PATH=/tmp/log.emergency.txt.xz
fi;

if [ -n "${2}" ]; then
        SUMMARY_PATH=$2
else
        SUMMARY_PATH="/dev/null"
fi;

echo "${LOG_PATH}"
(
    echo "TESTING IN PROGRESS - FAKE LOG FILE CONTENT"
    echo "########## PRINTER SUMMARY ##########";
    cat ${SUMMARY_PATH};
) | xz -T0 -0 > "${LOG_PATH}"
sync "${LOG_PATH}"
