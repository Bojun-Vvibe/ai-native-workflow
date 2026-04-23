#!/usr/bin/env bash
# Daily token-budget report wrapper, intended to be run by launchd.
#
# Responsibilities:
#   1. Locate python3.
#   2. Run the report for "yesterday" (full local day).
#   3. Write the markdown to ~/Reports/token-budget/YYYY-MM-DD.md.
#   4. Rotate: delete reports older than 90 days.
#   5. Exit non-zero on any failure so launchd records it.
#
# Customize the TRACKER_DIR and TRACKER_CMD for your setup.
set -eu

TRACKER_DIR="${TRACKER_DIR:-$HOME/Projects/ai-native-workflow/templates/token-budget-tracker}"
REPORT_DIR="${REPORT_DIR:-$HOME/Reports/token-budget}"
RETAIN_DAYS="${RETAIN_DAYS:-90}"

# Use the repo's pinned interpreter if present, else system python3.
PY="$(command -v python3)"
[ -x "$PY" ] || { echo "[run-daily-report] no python3 on PATH ($PATH)" >&2; exit 2; }

mkdir -p "$REPORT_DIR"

# Yesterday's date in local time.
yesterday="$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d 'yesterday' +%Y-%m-%d)"
out="$REPORT_DIR/$yesterday.md"

echo "[run-daily-report] $(date -Iseconds) writing $out"

# Run the tracker's report command. Adjust args to your tracker.
if [ -d "$TRACKER_DIR/src" ]; then
  ( cd "$TRACKER_DIR" && PYTHONPATH=src "$PY" -m report --days 1 --by model,phase ) >"$out"
else
  echo "[run-daily-report] TRACKER_DIR=$TRACKER_DIR not found" >&2
  exit 3
fi

# Rotate: prune reports older than RETAIN_DAYS.
find "$REPORT_DIR" -type f -name '*.md' -mtime +"$RETAIN_DAYS" -print -delete

echo "[run-daily-report] done"
