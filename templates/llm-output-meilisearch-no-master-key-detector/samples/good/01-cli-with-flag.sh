#!/usr/bin/env bash
# Good: master key passed via CLI flag from a secret store
set -e
KEY="$(cat /run/secrets/meili_master_key)"
./meilisearch --http-addr 0.0.0.0:7700 --env production --master-key "${KEY}"
