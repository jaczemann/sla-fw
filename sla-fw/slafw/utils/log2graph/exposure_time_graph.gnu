#set term qt font "arial,16" size 1600,900
set term svg font "arial,16" size 1600,900
set termoption dashed
set output '/dev/stdout'

set ylabel "Time [s]"
set xlabel "Project layer"

set grid xtics ytics mytics
set mytics 2
set grid
set style fill solid

plot \
	'/dev/stdin' using 1:($10/100.0) with boxes linecolor rgb "#bfffb5" title "RAM usage", \
	'/dev/stdin' using 1:($11/100.0) with boxes linecolor rgb "#e8dbff" title "CPU usage", \
	'/dev/stdin' using 1:4 with lines title "pixels", \
	'/dev/stdin' using 1:7 with lines title "resize", \
	'/dev/stdin' using 1:8 with lines title "screenshot", \
	'/dev/stdin' using 1:9 with lines title "pixels + resize + screenshot", \
	'/dev/stdin' using 1:2 with lines title "blank", \
	'/dev/stdin' using 1:3 with lines title "blit", \
	'/dev/stdin' using 1:6 with lines title "rename", \
	'/dev/stdin' using 1:5 with lines title "read file"
