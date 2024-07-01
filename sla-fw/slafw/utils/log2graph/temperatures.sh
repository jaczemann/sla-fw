#!/bin/zsh

# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

if [ "$#" -ne 1 ]; then
	BACKDAYS=365
else
	BACKDAYS=$1
fi
SECS=$((`date -d- +%s` - $BACKDAYS * 86400))

rm -f *job*
rm -f temperatures.pdf

for i in *.tar.xz; do echo "Splitting $i"; tar xf $i --to-stdout logs/log.txt | csplit --quiet --prefix="${${i#*.}%%.*}-job-" - "/PrinterState.RUNNING -> PrinterState.PRINTING/" "{*}"; done
for i in *-job-??; do echo "Splitting $i"; csplit --quiet --prefix=$i- $i "/PrinterState.PRINTING -> PrinterState.RUNNING/" "{*}"; done
rm -f *-job-??
# remove projects with unplugged temperature sensor(s)
#for i in `grep -l 'Temperatures \[C\].*-' *-job-??-??`; do echo "Removing $i" ; rm -f $i; done
for i in *-job-??-??; do echo -n "${i%%-*} - " > $i.time; grep 'Temperatures \[C\]' $i |head -n1|cut -d " " -f -3 >> $i.time; done
for i in *-job-??-??; do echo "Collecting data from $i"; grep 'Temperatures \[C\]' $i | cut -d " " -f 3,12- | ./linear_time.py > $i.csv; done
for i in *.csv; do [[ `wc -l $i|cut -d " " -f1 -` -lt 200 ]] && rm -f ${i%.csv}*; done
for i in *.time; do [[ `cat $i|cut -d " " -f3-|date -f- +%s` -lt $SECS ]] && rm -f ${i%.time}*; done
for i in *.csv; do echo "Plotting $i"; gnuplot -e "set title \"`cat ${i%.csv}.time`\"" temperature_graph.gnu < $i > ${i%.csv}.svg; done
for i in *.svg; do echo "Converting $i"; rsvg-convert -f pdf -o ${i%.svg}.pdf $i; done
pdfunite *job*.pdf temperatures.pdf
