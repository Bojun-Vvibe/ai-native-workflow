#!/usr/bin/env bash
set -euo pipefail

# Bring up a single-node Couchbase cluster.
couchbase-cli cluster-init \
  --cluster localhost:8091 \
  --cluster-username Administrator \
  --cluster-password password \
  --services data,index,query \
  --cluster-ramsize 1024
