#!/usr/bin/env tcsh
# bad/08_eval_after_pipe.tcsh — eval at command position after `|`.
# Even though piping into eval is unusual, the parser still accepts
# `cmd | eval $x` — flagged because $x is dynamic.
echo data | eval $handler
