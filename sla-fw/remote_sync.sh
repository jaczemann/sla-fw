#!/bin/sh

# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

SLA=$1

if [ -z ${SLA} ]; then
	echo "Pass target as the only argument";
	exit -1;
fi;

rsync -av systemd/slafw.service root@${SLA}:/lib/systemd/system/slafw.service &&
rsync -av systemd/slafw-tmpfiles.conf root@${SLA}:/lib/tmpfiles.d/slafw-tmpfiles.conf &&
rsync -av slafw/scripts/ root@${SLA}:/usr/share/slafw/scripts/ &&
rsync -av --exclude scripts --exclude __pycache__ slafw/ root@${SLA}:/usr/lib/python3.9/site-packages/slafw/

ssh root@${SLA} "
set -o xtrace; \
systemctl daemon-reload; \
systemctl restart slafw; \
systemctl restart model-detect.service
"
