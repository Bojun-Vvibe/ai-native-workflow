#!/usr/bin/env bash
# verify.sh — worked-example end-to-end check for the
# ssh-permitrootlogin-yes detector.
set -u
cd "$(dirname "$0")"

bad_total=0
bad_hit=0
for f in examples/bad/*; do
  bad_total=$((bad_total + 1))
  out="$(python3 detect.py "$f" || true)"
  if [ -n "$out" ]; then
    bad_hit=$((bad_hit + 1))
  else
    echo "MISS bad: $f" >&2
  fi
done

good_total=0
good_hit=0
for f in examples/good/*; do
  good_total=$((good_total + 1))
  out="$(python3 detect.py "$f" || true)"
  if [ -n "$out" ]; then
    good_hit=$((good_hit + 1))
    echo "FALSE POSITIVE good: $f -> $out" >&2
  fi
done

echo "bad=${bad_hit}/${bad_total} good=${good_hit}/${good_total}"
if [ "$bad_hit" -eq "$bad_total" ] && [ "$good_hit" -eq 0 ]; then
  echo "PASS"
  exit 0
fi
echo "FAIL"
exit 1
