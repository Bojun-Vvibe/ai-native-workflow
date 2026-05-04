#!/usr/bin/env bash
# Wrapper that invokes the python harness; exits 0 on PASS.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$HERE/test.py"
