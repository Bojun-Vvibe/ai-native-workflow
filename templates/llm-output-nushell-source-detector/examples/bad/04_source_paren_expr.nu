#!/usr/bin/env nu
# bad/04_source_paren_expr.nu — paren-expression result into source.
let cfg = "configs/init.nu"
source ($cfg | str trim)
