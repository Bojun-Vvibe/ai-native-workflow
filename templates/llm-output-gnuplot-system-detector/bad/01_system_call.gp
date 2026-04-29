# gnuplot script with system() shell escape
set terminal pngcairo size 800,600
set output "out.png"
plot sin(x)
# LLM helpfully added: "after rendering, convert to PDF"
system("convert out.png out.pdf")
