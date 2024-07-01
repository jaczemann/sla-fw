#set term qt font "arial,16" size 1600,900
set term svg font "arial,16" size 1600,900
set output '/dev/stdout'

IGNORE_BELOW=-20
filter(x)=(x>=IGNORE_BELOW)?(x):(1/0)

set ylabel "Temperature [°C]"
set yrange[20:65]
set xlabel "Project time [HH:MM]"

set xdata time
set timefmt "%s"
set format x "%H:%M"

set grid xtics ytics mytics
set mytics 2
set grid

plot \
	'/dev/stdin' u 1:(filter($3)) w l title "Ambient", \
	'/dev/stdin' u 1:(filter($2)) w l title "UV SL1", \
	'/dev/stdin' u 1:(filter($4)) w l title "UV SL1S", \
	'/dev/stdin' u 1:(filter($5)) w l title "Extra"
