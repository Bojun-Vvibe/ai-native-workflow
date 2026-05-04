#!/usr/bin/env bash
# Worked example: run the detector across every bad/ and good/ fixture
# and assert the expected verdict. Exits non-zero on any miss.
set -u
cd "$(dirname "$0")"

PASS=0
FAIL=0

assert_bad() {
  local f="$1"
  local out
  out="$(python3 detector.py "$f" 2>/dev/null || true)"
  local rc=$?
  if [ "$out" = "BAD" ]; then
    PASS=$((PASS + 1))
    echo "ok   bad   $f -> BAD"
  else
    FAIL=$((FAIL + 1))
    echo "FAIL bad   $f -> $out (rc=$rc)" >&2
  fi
}

assert_good() {
  local f="$1"
  local out
  out="$(python3 detector.py "$f" 2>/dev/null || true)"
  if [ "$out" = "GOOD" ]; then
    PASS=$((PASS + 1))
    echo "ok   good  $f -> GOOD"
  else
    FAIL=$((FAIL + 1))
    echo "FAIL good  $f -> $out" >&2
  fi
}

bad_total=0
bad_hit=0
for f in bad/case-*; do
  bad_total=$((bad_total + 1))
  out="$(python3 detector.py "$f" 2>/dev/null || true)"
  if [ "$out" = "BAD" ]; then
    bad_hit=$((bad_hit + 1))
  fi
  assert_bad "$f"
done

good_total=0
good_bad=0
for f in good/case-*; do
  good_total=$((good_total + 1))
  out="$(python3 detector.py "$f" 2>/dev/null || true)"
  if [ "$out" = "BAD" ]; then
    good_bad=$((good_bad + 1))
  fi
  assert_good "$f"
done

echo "summary: bad=${bad_hit}/${bad_total} BAD  good=${good_bad}/${good_total} BAD  pass=${PASS} fail=${FAIL}"
if [ "$FAIL" -ne 0 ]; then
  echo "RESULT: FAIL" >&2
  exit 1
fi
echo "RESULT: PASS"
exit 0
