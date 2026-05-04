#!/usr/bin/env bash
# Documented test fixture; the only literal token is the well-known
# dev-mode placeholder, and the line carries an explicit allow marker
# acknowledging the developer reviewed it.
set -euo pipefail

export VAULT_ADDR="http://127.0.0.1:8200"
export VAULT_TOKEN="root" # vault-root-token-allowed
vault status
