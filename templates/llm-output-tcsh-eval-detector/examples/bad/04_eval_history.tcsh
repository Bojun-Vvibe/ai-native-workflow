#!/usr/bin/env tcsh
# bad/04_eval_history.tcsh — !$ pulls the last word of the previous
# command and eval-executes it. Classic csh history-injection sink.
ls /tmp/foo
eval !$
