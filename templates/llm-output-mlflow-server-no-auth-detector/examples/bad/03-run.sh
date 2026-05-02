#!/usr/bin/env bash
set -euo pipefail
mlflow ui --host :: --port 5000 --backend-store-uri sqlite:///mlflow.db
