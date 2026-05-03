#!/usr/bin/env bash
# Provision a new namespace via Nacos OpenAPI -- using default creds.
# Anyone who can reach the console can do the same.
set -euo pipefail

NACOS_HOST="${NACOS_HOST:-nacos-server:8848}"

# Login (Nacos OpenAPI v1) with the published default credentials.
TOKEN=$(curl -sS -X POST "http://${NACOS_HOST}/nacos/v1/auth/login" \
  -d "username=nacos&password=nacos" | python3 -c 'import json,sys;print(json.load(sys.stdin)["accessToken"])')

# Equivalent shorthand:
curl -sS -u nacos:nacos "http://${NACOS_HOST}/nacos/v1/console/namespaces"

echo "token=${TOKEN}"
