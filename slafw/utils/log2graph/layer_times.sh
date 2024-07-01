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
rm -f layer_times.pdf

for i in *.tar.xz; do
	echo "Splitting $i"
	tar xf $i --to-stdout logs/log.txt | csplit --quiet --prefix="${${i#*.}%%.*}-job-" - "/PrinterState.RUNNING -> PrinterState.PRINTING/" "{*}"
done
for i in *-job-??; do
	echo "Splitting $i"
	csplit --quiet --prefix=$i- $i "/PrinterState.PRINTING -> PrinterState.RUNNING/" "{*}"
done
rm -f *-job-??
for i in *-job-??-??; do
	if `grep -q 'Layer started' $i` ; then
		echo -n "${i%%-*} - " > $i.time;
		grep 'Layer started' $i | head -n1 | cut -d " " -f -3 >> $i.time
	fi
done
for i in *.time; do [[ `cat $i|cut -d " " -f3-|date -f- +%s` -lt $SECS ]] && rm -f $i; done
for i in *-job-??-??; do
	if [ -f $i.time ]; then
		echo "Collecting data from $i"
		grep 'Layer started' $i | cut -d " " -f3,15,19,38,40 | sed -E "s/^([^ ]*) '([0-9]+).* \[([0-9]+)\], '([^'%]*)%', '([^'%]*)%'/\1 \2 \3 \4 \5/" | ./layer_diff.py > $i.csv
	fi
done
rm -f *-job-??-??
for i in *.csv; do [[ `wc -l $i|cut -d " " -f1 -` -lt 10 ]] && rm -f $i; done
for i in *.csv; do
	echo "Plotting $i";
	gnuplot -e "set title \"`cat ${i%.csv}.time`\"" layer_time_graph.gnu < $i > ${i%.csv}.svg
done
for i in *.svg; do echo "Converting $i"; rsvg-convert -f pdf -o ${i%.svg}.pdf $i; done
pdfunite *job*.pdf layer_times.pdf
