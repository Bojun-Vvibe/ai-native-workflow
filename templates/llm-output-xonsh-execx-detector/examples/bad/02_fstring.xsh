#!/usr/bin/env xonsh
# 02_fstring.xsh — f-string smuggles a variable into the source.
target = $ARG1
execx(f"git push origin {target}")
