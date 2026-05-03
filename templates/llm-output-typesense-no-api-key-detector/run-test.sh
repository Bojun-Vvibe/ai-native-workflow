#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
chmod +x detector.sh
./detector.sh examples/bad/* examples/good/*
