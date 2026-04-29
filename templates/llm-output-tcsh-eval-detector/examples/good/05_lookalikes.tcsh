#!/usr/bin/env tcsh
# good/05_lookalikes.tcsh — words that contain "eval" but are not
# the eval builtin at command position. Detector must not flag.
set evaluation = $1     # variable name happens to start with eval
echo "evaluator: $evaluation"
alias myeval 'echo not-the-builtin'
