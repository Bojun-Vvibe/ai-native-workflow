#!/usr/bin/env bash
# Operational script — explicitly re-enables protected mode if some
# previous run had toggled it off. This must NOT be flagged.
set -euo pipefail
redis-cli -h "$REDIS_HOST" -a "$REDIS_PASSWORD" CONFIG SET protected-mode yes
redis-cli -h "$REDIS_HOST" -a "$REDIS_PASSWORD" CONFIG REWRITE
