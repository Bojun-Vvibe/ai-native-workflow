#!/bin/bash
set -euo pipefail

exec /usr/bin/loki \
  -config.file=/etc/loki/loki.yaml \
  -auth.enabled=false \
  -target=all
