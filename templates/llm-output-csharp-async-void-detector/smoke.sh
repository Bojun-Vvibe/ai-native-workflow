#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

bad_out=$(python3 detect.py bad/ || true)
good_out=$(python3 detect.py good/ || true)

bad_hits=$(printf '%s\n' "$bad_out" | grep -Ec ':[0-9]+:[0-9]+:' || true)
good_hits=$(printf '%s\n' "$good_out" | grep -Ec ':[0-9]+:[0-9]+:' || true)

echo "bad_hits=$bad_hits"
echo "good_hits=$good_hits"

if [ "$bad_hits" -le 0 ]; then
    echo "FAIL: expected bad_hits > 0" >&2
    echo "$bad_out" >&2
    exit 1
fi
if [ "$good_hits" -ne 0 ]; then
    echo "FAIL: expected good_hits == 0" >&2
    echo "$good_out" >&2
    exit 1
fi
echo "OK: bad=$bad_hits good=$good_hits"
