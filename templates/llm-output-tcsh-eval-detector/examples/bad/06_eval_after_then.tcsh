#!/usr/bin/env tcsh
# bad/06_eval_after_then.tcsh — eval inside an `if ... then` branch.
if ( $#argv > 0 ) then
    eval $argv[1]
endif
