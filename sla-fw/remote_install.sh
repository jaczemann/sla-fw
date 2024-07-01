#!/bin/sh

# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

CFG="/etc/sl1fw/hardware.cfg"

# Resolve target
if [ "$#" -ne 1 ]; then
    echo "Please provide target ip as the only argument"
    exit -1
fi
target=${1}
echo "Target is ${target}"

# Print commands being executed
set -o xtrace

# Create temp root
tmp=$(mktemp --directory --tmpdir=/tmp/ slafw.XXXX)
echo "Local temp is ${tmp}"

echo "Running setup"
python3 setup.py sdist --dist-dir=${tmp}

# Create remote temp
target_tmp=$(ssh root@${target} "mktemp --directory --tmpdir=/tmp/ slafw.XXXX")
echo "Remote temp is ${target_tmp}"

echo "Installing on target"
scp -r ${tmp}/* root@${target}:${target_tmp}
ssh root@${target} "\
set -o xtrace; \
cp -f \"$CFG\" \"$CFG.bak\"; \
cd ${target_tmp}; \
tar xvf slafw*.tar.gz; \
rm slafw*.tar.gz; \
cd slafw-*; \
mount -o remount,rw /usr/share/factory/defaults; \
pip3 install . ; \
mount -o remount,ro /usr/share/factory/defaults; \
mv -f \"$CFG\" \"$CFG.new\"; \
cp \"$CFG.bak\" \"$CFG\"; \
systemctl daemon-reload; \
systemctl restart slafw; \
systemctl restart model-detect.service
"

echo "Removing remote temp"
ssh root@${target} "rm -rf ${target_tmp}"

echo "Removing local temp"
rm -rf ${tmp}
