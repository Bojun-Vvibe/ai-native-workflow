#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"

bad_files=(examples/bad/*/*)
good_files=(examples/good/*/*)
BAD_TOTAL=${#bad_files[@]}
GOOD_TOTAL=${#good_files[@]}

bad_hits=0
for f in "${bad_files[@]}"; do
  python3 detector.py "$f" >/dev/null 2>&1
  rc=$?
  if [ "$rc" -gt 0 ]; then bad_hits=$((bad_hits + 1)); fi
done

good_hits=0
for f in "${good_files[@]}"; do
  python3 detector.py "$f" >/dev/null 2>&1
  rc=$?
  if [ "$rc" -gt 0 ]; then good_hits=$((good_hits + 1)); fi
done

echo "bad=${bad_hits}/${BAD_TOTAL} good=${good_hits}/${GOOD_TOTAL}"
if [ "$bad_hits" -eq "$BAD_TOTAL" ] && [ "$good_hits" -eq 0 ]; then
  echo "PASS"; exit 0
fi
echo "FAIL"; exit 1
