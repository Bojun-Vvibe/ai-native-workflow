#!/usr/bin/env bash
# verify.sh — prove the detector fires on bad/ and stays silent on good/.
# Exits 0 only if both halves pass.
set -u

cd "$(dirname "$0")"

echo "=== detector vs bad/ (expect findings, non-zero exit) ==="
bad_out=$(python3 detector.py bad/ 2>&1)
bad_exit=$?
echo "$bad_out"
echo "exit=$bad_exit"

if [ "$bad_exit" -eq 0 ]; then
  echo "FAIL: detector returned 0 on bad/ — expected >0"
  exit 1
fi
bad_findings=$(echo "$bad_out" | grep -c ':[0-9]*:')
if [ "$bad_findings" -lt 1 ]; then
  echo "FAIL: no findings printed for bad/"
  exit 1
fi

echo
echo "=== detector vs good/ (expect 0 findings, exit 0) ==="
good_out=$(python3 detector.py good/ 2>&1)
good_exit=$?
echo "$good_out"
echo "exit=$good_exit"

if [ "$good_exit" -ne 0 ]; then
  echo "FAIL: detector returned $good_exit on good/ — expected 0"
  exit 1
fi
good_findings=$(echo "$good_out" | grep -c ':[0-9]*:' || true)
if [ "$good_findings" -ne 0 ]; then
  echo "FAIL: detector reported $good_findings findings on good/ — expected 0"
  exit 1
fi

echo
echo "PASS: bad=${bad_findings} findings (exit ${bad_exit}), good=0 findings (exit 0)"
exit 0
