# Plain plotting script - no shell escapes.
set terminal pngcairo size 800,600
set output "out.png"
set title "linear demo"
plot x with lines
