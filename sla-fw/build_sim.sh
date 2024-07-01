#!/bin/sh

BOARD=6 SIMULATION=1 make -C dependencies/mc-fw/SLA-control-01 -j5 &&
mv dependencies/mc-fw/SLA-control-01/SLA-control_rev06.elf ./SLA-control-01.elf

