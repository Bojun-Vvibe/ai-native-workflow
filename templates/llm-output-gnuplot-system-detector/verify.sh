#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"

echo "== bad/ =="
bad_out=$(python3 detector.py bad/ 2>&1) || true
echo "$bad_out"
bad_n=$(grep -c '^bad/' <<<"$bad_out" || true)

echo
echo "== good/ =="
good_out=$(python3 detector.py good/ 2>&1) || true
echo "$good_out"
good_n=$(grep -c '^good/' <<<"$good_out" || true)

echo
echo "-- summary --"
echo "bad-findings:  $bad_n  (expected: >= 6)"
echo "good-findings: $good_n (expected: 0)"

if [ "$bad_n" -ge 6 ] && [ "$good_n" -eq 0 ]; then
    echo "PASS"
    exit 0
fi
echo "FAIL"
exit 1
