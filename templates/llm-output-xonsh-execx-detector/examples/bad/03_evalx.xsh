#!/usr/bin/env xonsh
# 03_evalx.xsh — evalx on a captured subprocess output.
result = evalx($(echo $USER_QUERY))
print(result)
