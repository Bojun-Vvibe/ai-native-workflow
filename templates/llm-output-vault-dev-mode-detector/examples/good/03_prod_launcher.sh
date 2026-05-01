#!/usr/bin/env bash
set -euo pipefail
# Production launcher: real config, real seal, no dev shortcuts.
exec vault server -config=/etc/vault/vault.hcl
