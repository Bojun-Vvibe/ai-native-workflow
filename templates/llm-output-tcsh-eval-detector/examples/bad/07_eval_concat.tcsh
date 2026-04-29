#!/usr/bin/env tcsh
# bad/07_eval_concat.tcsh — concatenation of literal + var inside dq.
set tail = "; rm -rf /tmp/work"
eval "echo running $tail"
