#!/usr/bin/env bash
set -euo pipefail

# Generate fresh creds at boot; never the documented default.
export MINIO_ROOT_USER="admin"
export MINIO_ROOT_PASSWORD="$(openssl rand -hex 24)"

minio server /data --console-address ":9001"
