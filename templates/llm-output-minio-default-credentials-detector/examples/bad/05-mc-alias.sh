#!/usr/bin/env bash
set -euo pipefail
mc alias set local http://127.0.0.1:9000 minioadmin minioadmin
mc admin info local
