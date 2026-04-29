#!/usr/bin/env bash
# Smoke test: bad must produce >0 findings, good must produce 0.
set -u
cd "$(dirname "$0")"

bad_n=$(python3 detect.py examples/bad.erl | grep -c ':')
good_n=$(python3 detect.py examples/good.erl | grep -c ':')

echo "bad findings:  $bad_n"
echo "good findings: $good_n"

if [ "$bad_n" -gt 0 ] && [ "$good_n" -eq 0 ]; then
    echo "OK"
    exit 0
fi
echo "FAIL"
exit 1
