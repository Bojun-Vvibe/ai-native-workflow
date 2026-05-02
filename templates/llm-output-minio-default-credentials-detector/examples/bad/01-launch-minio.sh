#!/usr/bin/env bash
set -euo pipefail

export MINIO_ROOT_USER=minioadmin
export MINIO_ROOT_PASSWORD=minioadmin

minio server /data
