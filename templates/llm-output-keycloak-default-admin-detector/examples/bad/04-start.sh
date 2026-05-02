#!/usr/bin/env bash
# Bootstrap a single-node identity provider for local prod-shaped tests.
set -euo pipefail
exec /opt/keycloak/bin/kc.sh start \
  --hostname=idp.example.com \
  --bootstrap-admin-username admin \
  --bootstrap-admin-password admin
