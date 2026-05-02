#!/usr/bin/env bash
# mlflow-auth-external — auth enforced by oauth2-proxy in front of this server.
set -euo pipefail
mlflow server --host 0.0.0.0 --port 5000 \
  --backend-store-uri sqlite:///mlflow.db \
  --default-artifact-root /mlruns
