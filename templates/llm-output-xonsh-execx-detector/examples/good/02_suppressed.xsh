#!/usr/bin/env xonsh
# 02_suppressed.xsh — audited dynamic call honored via marker.
bootstrap = open("/etc/trusted-bootstrap.xsh").read()
execx(bootstrap)  # execx-ok: file is root-owned chmod 600, audited 2026-04
