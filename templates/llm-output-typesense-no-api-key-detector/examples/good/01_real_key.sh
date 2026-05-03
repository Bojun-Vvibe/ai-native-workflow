#!/usr/bin/env bash
# admin key sourced from a secret manager at boot, rotated quarterly
: "${TS_ADMIN_KEY:?must be injected by the secret broker}"
typesense-server \
  --data-dir=/var/lib/typesense \
  --api-key="${TS_ADMIN_KEY}" \
  --listen-address=127.0.0.1
