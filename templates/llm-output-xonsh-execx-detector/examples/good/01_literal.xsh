#!/usr/bin/env xonsh
# 01_literal.xsh — purely literal source, no variables. Safe.
execx("echo hello")
execx('print("static banner")')
result = evalx("1 + 2")
