#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"

BAD_TOTAL=$(find examples/bad -type f | wc -l | tr -d ' ')
GOOD_TOTAL=$(find examples/good -type f | wc -l | tr -d ' ')

bad_hits=0
while IFS= read -r f; do
  python3 detector.py "$f" >/dev/null 2>&1
  rc=$?
  if [ "$rc" -gt 0 ]; then bad_hits=$((bad_hits + 1)); fi
done < <(find examples/bad -type f)

good_hits=0
while IFS= read -r f; do
  python3 detector.py "$f" >/dev/null 2>&1
  rc=$?
  if [ "$rc" -gt 0 ]; then good_hits=$((good_hits + 1)); fi
done < <(find examples/good -type f)

echo "bad=${bad_hits}/${BAD_TOTAL} good=${good_hits}/${GOOD_TOTAL}"
if [ "$bad_hits" -eq "$BAD_TOTAL" ] && [ "$good_hits" -eq 0 ]; then
  echo "PASS"; exit 0
fi
echo "FAIL"; exit 1
