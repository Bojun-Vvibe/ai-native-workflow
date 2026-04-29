#!/usr/bin/env nu
# good/04_suppressed.nu — both lines audited and suppressed.
let cfg = "configs/init.nu"
source $cfg # source-ok
nu -c $"ls" # nu-c-ok
