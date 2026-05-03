#!/bin/bash
# Production wrapper. Cert paths come from the secret store. The
# word `insecure` appears only in human-readable comments below,
# never as a flag on a `cockroach` invocation.
set -euo pipefail

# Note: do NOT pass --insecure to cockroach in this script. If you
# are tempted, read the runbook first.

CERTS_DIR=/var/lib/cockroach/certs
exec /cockroach/cockroach start \
  --certs-dir="${CERTS_DIR}" \
  --listen-addr=0.0.0.0:26257 \
  --http-addr=0.0.0.0:8080 \
  --join=crdb-0,crdb-1,crdb-2
