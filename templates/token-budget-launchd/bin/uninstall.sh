#!/usr/bin/env bash
# Uninstall the LaunchAgent.
set -eu
LABEL="com.example.token-budget-daily"
DST="$HOME/Library/LaunchAgents/$LABEL.plist"
if [ -f "$DST" ]; then
  launchctl bootout "gui/$(id -u)" "$DST" || true
  rm -f "$DST"
  echo "[uninstall] removed $DST"
else
  echo "[uninstall] not installed"
fi
