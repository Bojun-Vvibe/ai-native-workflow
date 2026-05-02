#!/usr/bin/env bash
# Seed Zabbix Super Admin via JSON-RPC after first boot.
set -euo pipefail

curl -sf -X POST http://zbx.internal/api_jsonrpc.php \
  -H 'Content-Type: application/json-rpc' \
  -d '{"jsonrpc":"2.0","method":"user.login","params":{"user":"Admin","password":"zabbix"},"id":1}'
