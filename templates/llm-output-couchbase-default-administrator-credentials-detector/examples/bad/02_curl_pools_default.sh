#!/usr/bin/env bash
set -eu
# Bootstrap the cluster via the REST endpoint directly.
curl -sS -u Administrator:couchbase \
  -X POST http://node-01.example.lan:8091/pools/default \
  -d 'memoryQuota=1024'
