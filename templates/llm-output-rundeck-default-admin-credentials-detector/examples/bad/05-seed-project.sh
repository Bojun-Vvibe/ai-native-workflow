#!/usr/bin/env bash
# Seed Rundeck project after first boot via API.
set -euo pipefail

curl -sf -u admin:admin \
  -X POST "https://rundeck.internal/api/45/projects" \
  -H 'Content-Type: application/json' \
  -d '{"name":"core"}'
