#!/usr/bin/env tcsh
# good/04_suppressed.tcsh — audited line, suppressed.
set cmd = "uname -a"
eval $cmd  # eval-ok: $cmd built from a closed allow-list above
