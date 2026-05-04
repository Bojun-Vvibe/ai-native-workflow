#!/usr/bin/env bash
# launch code-server with password auth behind a reverse proxy
set -e
exec code-server --bind-addr 127.0.0.1:8080 --auth password /workspace
