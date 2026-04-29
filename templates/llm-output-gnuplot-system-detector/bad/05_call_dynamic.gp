# `call` with a path built via string concatenation.
base = "scripts/"
name = "render"
call base . name . ".gp" "arg1"
