#!/usr/bin/env bash
set -euo pipefail

export MINIO_ROOT_USER="${MINIO_ROOT_USER:?must be set out-of-band}"
export MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:?must be set out-of-band}"

minio server /data
