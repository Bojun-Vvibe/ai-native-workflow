#!/usr/bin/env bash
set -euo pipefail

helm upgrade --install superset superset/superset \
  --namespace analytics \
  --set superset.secretKey=your_secret_key_here \
  --set postgresql.enabled=true
