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
rm -f exposure_times.pdf

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
		echo "Splitting $i"
		csplit --quiet --prefix=$i-layer_ --suffix-format="%04d" $i "/Layer started/" "{*}"
	fi
done
rm -f *-job-??-??
rm -f *-job-??-??-layer_000[01]
for i in *-job-??-??-layer_????; do
	echo "Collecting data from $i"
	echo -n "${i#*-job-??-??-layer_} " > $i.csv
	grep 'slafw.image.*secs' $i | cut -d " " -f10- | sort | uniq | sed -E "{s/.* ([.0-9]*) secs.*/\1/g}" | tr "\n" " " >> $i.csv
	grep 'Layer started' $i |  cut -d "'" -f24,28 | tr -d "'" | tr "%" " " >> $i.csv
	[[ `wc -w $i.csv|cut -d " " -f1 -` -lt 11 ]] && rm -f $i.csv;
done
for i in *.time; do
	echo "Joining ${i%.time}.csv"
	cat ${i%.time}-layer_????.csv > ${i%.time}.csv
done
rm -f *-job-??-??-layer_*
for i in *.csv; do [[ `wc -l $i|cut -d " " -f1 -` -lt 10 ]] && rm -f $i; done
for i in *.csv; do
	echo "Plotting $i";
	gnuplot -e "set title \"`cat ${i%.csv}.time`\"" exposure_time_graph.gnu < $i > ${i%.csv}.svg
done
for i in *.svg; do echo "Converting $i"; rsvg-convert -f pdf -o ${i%.svg}.pdf $i; done
pdfunite *job*.pdf exposure_times.pdf
