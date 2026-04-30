#!/usr/bin/env xonsh
# 05_format.xsh — old-style .format() call still produces a dynamic source.
template = "cd {} && make {}"
execx(template.format(workdir, target))
