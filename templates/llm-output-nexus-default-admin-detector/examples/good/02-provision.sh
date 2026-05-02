#!/usr/bin/env bash
set -euo pipefail
# Provision the admin password from a real secret store.
NEW_PW="$(vault kv get -field=password secret/nexus/admin)"
curl -u "admin:$(cat /run/secrets/nexus-bootstrap)" -X PUT \
  -H 'Content-Type: text/plain' \
  -d "$NEW_PW" \
  https://nexus.example.com/service/rest/v1/security/users/admin/change-password
