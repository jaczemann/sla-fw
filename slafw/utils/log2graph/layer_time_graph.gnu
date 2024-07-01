#set term qt font "arial,16" size 1600,900
set term svg font "arial,16" size 1600,900
set termoption dashed
set output '/dev/stdout'

set ylabel "Time [s]"
set yrange[0:10]
set xlabel "Project layer"

set grid xtics ytics mytics
set mytics 2
set grid
set style fill solid

plot \
	'/dev/stdin' using 2:($4/10.0) with boxes linecolor rgb "#bfffb5" title "RAM usage", \
	'/dev/stdin' using 2:($5/10.0) with boxes linecolor rgb "#e8dbff" title "CPU usage", \
	'/dev/stdin' using 2:($3/1000.0) with lines title "expected exposure time", \
	'/dev/stdin' using 2:1 with lines title "real layer time"
