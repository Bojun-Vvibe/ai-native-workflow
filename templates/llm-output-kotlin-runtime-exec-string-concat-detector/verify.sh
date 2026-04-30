#!/usr/bin/env bash
# verify.sh — worked example for kotlin Runtime.exec string-concat detector.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

MIN_BAD=7

bad_out="$(python3 detect.py examples/bad 2>&1)"
bad_rc=$?
bad_count="$(printf '%s\n' "$bad_out" | grep -cE ':(runtime-exec-string-interp|runtime-exec-array-interp|process-builder-string-interp|process-builder-list-interp|process-builder-command-set):')"

good_out="$(python3 detect.py examples/good 2>&1)"
good_rc=$?
good_count="$(printf '%s\n' "$good_out" | grep -cE ':(runtime-exec-string-interp|runtime-exec-array-interp|process-builder-string-interp|process-builder-list-interp|process-builder-command-set):')"

echo "bad findings:  $bad_count (rc=$bad_rc)"
echo "good findings: $good_count (rc=$good_rc)"

fail=0
[ "$bad_count" -lt "$MIN_BAD" ] && { echo "FAIL: expected >= $MIN_BAD bad, got $bad_count" >&2; fail=1; }
[ "$bad_rc" -ne 1 ] && { echo "FAIL: bad/ exit code should be 1, got $bad_rc" >&2; fail=1; }
[ "$good_count" -ne 0 ] && { echo "FAIL: expected 0 good findings, got $good_count" >&2; fail=1; }
[ "$good_rc" -ne 0 ] && { echo "FAIL: good/ exit code should be 0, got $good_rc" >&2; fail=1; }

if [ "$fail" -eq 0 ]; then
  echo "PASS"
  exit 0
fi
exit 1
