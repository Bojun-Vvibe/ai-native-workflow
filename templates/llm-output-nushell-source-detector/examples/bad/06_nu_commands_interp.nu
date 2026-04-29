#!/usr/bin/env nu
# bad/06_nu_commands_interp.nu — interpolated `--commands` argument.
let target = "release"
nu --commands $"do build ($target)"
