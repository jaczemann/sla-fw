#!/usr/bin/env bash

# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

if [ -n "${1}" ]; then
        LOG_PATH=$1
else
        exit 1
fi;

echo "${LOG_PATH}"
(
        for i in $(journalctl --list-boots | awk '{print $1}'); do
                echo "########## REBOOT: ${i} ##########";
                journalctl --output=short-precise --no-pager --boot "${i}";
        done;
) > "${LOG_PATH}"
sync "${LOG_PATH}"
