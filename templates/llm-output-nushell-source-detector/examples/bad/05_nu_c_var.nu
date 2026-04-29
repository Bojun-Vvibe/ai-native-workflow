#!/usr/bin/env nu
# bad/05_nu_c_var.nu — variable into `nu -c` is a code-injection sink.
let cmd = "ls | length"
nu -c $cmd
