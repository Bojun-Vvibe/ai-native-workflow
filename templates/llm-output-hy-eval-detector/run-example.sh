#!/usr/bin/env bash
# Run the Hy dynamic-eval detector against bundled examples.
set -u
cd "$(dirname "$0")"
echo "=== bad/ (expect findings) ==="
python3 detector.py examples/bad
bad_rc=$?
echo
echo "=== good/ (expect zero findings) ==="
python3 detector.py examples/good
good_rc=$?
echo
echo "bad findings (rc): $bad_rc"
echo "good findings (rc): $good_rc"
if [ "$bad_rc" -ge 6 ] && [ "$good_rc" -eq 0 ]; then
  echo "OK"
  exit 0
fi
echo "FAIL"
exit 1
