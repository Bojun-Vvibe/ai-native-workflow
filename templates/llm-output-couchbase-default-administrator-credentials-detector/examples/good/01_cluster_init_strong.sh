#!/usr/bin/env bash
set -euo pipefail

# Bootstrap with a high-entropy password from the secret manager.
CB_PW="$(openssl rand -base64 32)"
couchbase-cli cluster-init \
  --cluster localhost:8091 \
  --cluster-username Administrator \
  --cluster-password "${CB_PW}" \
  --services data,index,query \
  --cluster-ramsize 4096

# do NOT keep --cluster-password password in production
