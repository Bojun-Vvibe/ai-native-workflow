#!/usr/bin/env bash
# Bootstrap script that flips protected mode off at runtime so a
# clustered worker pool can connect without configuring auth first.
set -euo pipefail
redis-cli -h "$REDIS_HOST" CONFIG SET protected-mode no
redis-cli -h "$REDIS_HOST" CONFIG REWRITE
