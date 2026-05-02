#!/usr/bin/env bash
# Local dev only: bound to loopback. Port-forwarded by the developer
# manually when needed.
set -euo pipefail
mlflow server --host 127.0.0.1 --port 5000 \
  --backend-store-uri sqlite:///mlflow.db \
  --default-artifact-root ./mlruns
