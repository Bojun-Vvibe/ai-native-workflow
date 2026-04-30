#!/usr/bin/env xonsh
# 07_pct_format.xsh — %-formatted source.
execx("kubectl --context=%s apply -f -" % ctx)
