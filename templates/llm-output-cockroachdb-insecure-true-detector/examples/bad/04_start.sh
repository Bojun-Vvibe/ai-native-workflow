#!/bin/bash
# Wrapper generated when an LLM was asked to "make `cockroach sql`
# work without me having to deal with certs". Sets the env override
# that the official entrypoint reads on startup.
set -euo pipefail
export COCKROACH_INSECURE=true
exec /cockroach/cockroach start-single-node \
  --listen-addr=0.0.0.0:26257 \
  --http-addr=0.0.0.0:8080
