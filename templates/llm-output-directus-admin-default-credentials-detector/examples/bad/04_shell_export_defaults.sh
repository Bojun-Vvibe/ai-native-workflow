#!/usr/bin/env bash
set -euo pipefail

# Bootstrap the Directus instance for first-run.
export ADMIN_EMAIL="admin@example.com"
export ADMIN_PASSWORD="admin"
export KEY="$(openssl rand -hex 16)"
export SECRET="$(openssl rand -hex 16)"

npx directus bootstrap
