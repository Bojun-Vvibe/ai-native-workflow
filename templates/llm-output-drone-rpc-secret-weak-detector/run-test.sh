#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 detector.py examples/bad/* examples/good/*
