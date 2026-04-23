#!/usr/bin/env bash
# uninstall.sh — bootout and remove the symlink. Idempotent.
set -eu

LABEL="${LABEL:-com.example.anomaly-alert-daily}"
DST_PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$DST_PLIST"

echo "uninstalled: $LABEL"
echo "state preserved at: ${XDG_STATE_HOME:-$HOME/.local/state}/anomaly-alert/"
echo "remove state with:  rm -rf '${XDG_STATE_HOME:-$HOME/.local/state}/anomaly-alert/'"
