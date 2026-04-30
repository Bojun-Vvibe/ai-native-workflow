#!/usr/bin/env bash
# Verify the detector flags every bad fixture and no good fixture.
set -u
cd "$(dirname "$0")"

EXPECTED_BAD=6
EXPECTED_GOOD=0

bad_out=$(python3 detector.py fixtures/bad/ || true)
bad_count=$(printf "%s\n" "$bad_out" | grep -c ":" || true)
[ -z "$bad_out" ] && bad_count=0

good_out=$(python3 detector.py fixtures/good/ || true)
good_count=$(printf "%s\n" "$good_out" | grep -c ":" || true)
[ -z "$good_out" ] && good_count=0

echo "bad findings: $bad_count (expected $EXPECTED_BAD)"
echo "good findings: $good_count (expected $EXPECTED_GOOD)"

fail=0
[ "$bad_count" = "$EXPECTED_BAD" ] || { echo "FAIL: bad count mismatch"; fail=1; }
[ "$good_count" = "$EXPECTED_GOOD" ] || { echo "FAIL: good count mismatch"; fail=1; }

if [ "$fail" = 0 ]; then
  echo "PASS"
  exit 0
fi
exit 1
