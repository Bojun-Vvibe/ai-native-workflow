# Static `load` and `call` of a literal script path - safe, not flagged.
load "lib/colors.gp"
call "lib/render.gp"
plot sin(x)
