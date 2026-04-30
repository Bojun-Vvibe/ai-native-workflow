#!/usr/bin/env xonsh
# 06_low_level.xsh — bypassing execx by reaching into the execer directly
# is the same hazard with one extra layer of indirection.
src = open("/tmp/snippet.xsh").read()
__xonsh__.execer.exec(src)
