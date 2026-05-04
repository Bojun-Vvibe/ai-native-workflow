#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"

bad_total=0
bad_hit=0
for f in bad/*; do
  bad_total=$((bad_total + 1))
  if python3 detector.py "$f" >/dev/null; then
    : # exit 0 means no findings
  else
    bad_hit=$((bad_hit + 1))
  fi
done

good_total=0
good_hit=0
for f in good/*; do
  good_total=$((good_total + 1))
  if ! python3 detector.py "$f" >/dev/null; then
    good_hit=$((good_hit + 1))
  fi
done

echo "bad: ${bad_hit}/${bad_total}"
echo "good (false positives): ${good_hit}/${good_total}"

if [[ "${bad_hit}" -eq "${bad_total}" && "${good_hit}" -eq 0 ]]; then
  echo "PASS"
  exit 0
fi
echo "FAIL"
exit 1
