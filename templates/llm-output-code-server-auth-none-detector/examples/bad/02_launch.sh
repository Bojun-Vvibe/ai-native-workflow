#!/usr/bin/env bash
# launch code-server in a homelab container
set -e
exec code-server --bind-addr 0.0.0.0:8080 --auth none /workspace
