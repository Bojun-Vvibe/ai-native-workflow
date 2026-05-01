#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"

BAD_TOTAL=$(find examples/bad -type f | wc -l | tr -d ' ')
GOOD_TOTAL=$(find examples/good -type f | wc -l | tr -d ' ')

bad_hits=0
for f in examples/bad/*; do
  python3 detector.py "$f" >/dev/null 2>&1
  rc=$?
  if [ "$rc" -gt 0 ]; then bad_hits=$((bad_hits + 1)); fi
done

good_hits=0
for f in examples/good/*; do
  python3 detector.py "$f" >/dev/null 2>&1
  rc=$?
  if [ "$rc" -gt 0 ]; then good_hits=$((good_hits + 1)); fi
done

echo "bad=${bad_hits}/${BAD_TOTAL} good=${good_hits}/${GOOD_TOTAL}"
if [ "$bad_hits" -eq "$BAD_TOTAL" ] && [ "$good_hits" -eq 0 ]; then
  echo "PASS"; exit 0
fi
echo "FAIL"; exit 1
