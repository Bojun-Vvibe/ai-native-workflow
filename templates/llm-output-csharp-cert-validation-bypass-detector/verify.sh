#!/usr/bin/env bash
# verify.sh — worked-example end-to-end check for cert-validation detector.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

MIN_BAD=7

KIND_RE=': (dangerous-accept-any-validator|callback-return-true-lambda|callback-return-true-lambda-block|callback-return-true-delegate|callback-return-true-lambda-multiline|callback-return-true-lambda-multiline-block|callback-ctor-return-true):'

bad_out="$(python3 detect.py examples/bad 2>&1)"
bad_rc=$?
bad_count="$(printf '%s\n' "$bad_out" | grep -cE "$KIND_RE")"

good_out="$(python3 detect.py examples/good 2>&1)"
good_rc=$?
good_count="$(printf '%s\n' "$good_out" | grep -cE "$KIND_RE")"

echo "bad findings:  $bad_count (rc=$bad_rc)"
echo "good findings: $good_count (rc=$good_rc)"

fail=0
if [ "$bad_count" -lt "$MIN_BAD" ]; then
  echo "FAIL: expected >= $MIN_BAD findings in examples/bad, got $bad_count" >&2
  fail=1
fi
if [ "$bad_rc" -ne 1 ]; then
  echo "FAIL: detector exit code on bad/ should be 1, got $bad_rc" >&2
  fail=1
fi
if [ "$good_count" -ne 0 ]; then
  echo "FAIL: expected 0 findings in examples/good, got $good_count" >&2
  fail=1
fi
if [ "$good_rc" -ne 0 ]; then
  echo "FAIL: detector exit code on good/ should be 0, got $good_rc" >&2
  fail=1
fi

if [ "$fail" -eq 0 ]; then
  echo "PASS"
  exit 0
fi
exit 1
