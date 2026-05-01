#!/usr/bin/env bash
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
good_clean=0
for f in examples/good/*; do
  good_total=$((good_total + 1))
  out="$(python3 detect.py "$f" || true)"
  if [ -z "$out" ]; then
    good_clean=$((good_clean + 1))
  else
    echo "FALSE POSITIVE good: $f" >&2
    echo "$out" >&2
  fi
done

echo "bad=${bad_hit}/${bad_total} good=${good_clean}/${good_total}"
[ "$bad_hit" = "$bad_total" ] && [ "$good_clean" = "$good_total" ]
