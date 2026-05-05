#!/usr/bin/env bash
# run-tests.sh — assert detector flags all bad/* and none of good/*
set -u
cd "$(dirname "$0")"

chmod +x detect.sh

bad_pass=0
bad_total=0
for f in examples/bad/*.conf; do
  bad_total=$((bad_total + 1))
  if ./detect.sh "$f" >/dev/null; then
    echo "FAIL: bad sample not flagged (detector exited 0): $f"
  else
    bad_pass=$((bad_pass + 1))
  fi
done

good_fail=0
good_total=0
for f in examples/good/*.conf; do
  good_total=$((good_total + 1))
  if ./detect.sh "$f" >/dev/null; then
    : # exit 0 = clean = correct for good sample
  else
    echo "FAIL: good sample falsely flagged: $f"
    good_fail=$((good_fail + 1))
  fi
done

good_clean=$((good_total - good_fail))
echo "bad=${bad_pass}/${bad_total} good=${good_clean}/${good_total}"

if [ "$bad_pass" -eq "$bad_total" ] && [ "$good_fail" -eq 0 ]; then
  echo "PASS"
  exit 0
fi
echo "OVERALL FAIL"
exit 1
