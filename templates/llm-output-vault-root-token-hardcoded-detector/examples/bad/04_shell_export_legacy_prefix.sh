#!/usr/bin/env bash
# Bootstrap script left in the repo "for convenience". The s. prefix is
# the legacy Vault service-token prefix; this one was minted by the
# initial root token and never rotated.
set -euo pipefail

export VAULT_ADDR="https://vault.internal.example.org:8200"
export VAULT_TOKEN="s.aB3cDeFgHiJkLmNoPqRsTuVwXyZ0123456789"
export VAULT_NAMESPACE="platform/admin"

vault kv get secret/data/prod/db
