/* 05_interpret_concat.rexx
   INTERPRET on a concatenated string is the same hazard with extra
   steps: the runtime source includes a substring from input. */
parse arg name
src = 'say "hello, ' || name || '"'
interpret src
exit 0
