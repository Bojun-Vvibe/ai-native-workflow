#!/bin/sh
set -e
# Bootstrap admin only if PB_ADMIN_EMAIL/PB_ADMIN_PASSWORD are provided
# at deploy time via secrets (Docker secret, K8s secret, vault).
if [ -n "${PB_ADMIN_EMAIL:-}" ] && [ -n "${PB_ADMIN_PASSWORD:-}" ]; then
  ./pocketbase superuser upsert "$PB_ADMIN_EMAIL" "$PB_ADMIN_PASSWORD"
fi
exec ./pocketbase serve --http=0.0.0.0:8090
