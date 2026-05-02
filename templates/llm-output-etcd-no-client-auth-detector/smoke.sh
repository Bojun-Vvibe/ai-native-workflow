#!/usr/bin/env bash
# smoke.sh — assert detector flags all bad fixtures and no good fixtures.
set -u

cd "$(dirname "$0")"
chmod +x detector.sh

bad_files=(fixtures/bad/*)
good_files=(fixtures/good/*)
bad_total=${#bad_files[@]}
good_total=${#good_files[@]}

bad_flagged=0
for f in "${bad_files[@]}"; do
  out=$(./detector.sh "$f")
  if [ -n "$out" ]; then
    bad_flagged=$((bad_flagged + 1))
  else
    echo "DIFF: expected FLAG on $f, got nothing"
  fi
done

good_flagged=0
for f in "${good_files[@]}"; do
  out=$(./detector.sh "$f")
  if [ -n "$out" ]; then
    good_flagged=$((good_flagged + 1))
    echo "DIFF: unexpected FLAG on $f:"
    echo "$out"
  fi
done

echo "bad=${bad_flagged}/${bad_total} good=${good_flagged}/${good_total}"

if [ "$bad_flagged" -eq "$bad_total" ] && [ "$good_flagged" -eq 0 ]; then
  echo "PASS"
  exit 0
fi
echo "FAIL"
exit 1
