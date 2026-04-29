#!/usr/bin/env nu
# bad/01_source_var.nu — `source $var` is dynamic; the executed script
# is not audit-controlled.
let cfg = "configs/init.nu"
source $cfg
