#!/usr/bin/env bash
# Install the LaunchAgent. Idempotent.
set -eu
HERE="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.example.token-budget-daily"
SRC="$HERE/plist/$LABEL.plist"
DST="$HOME/Library/LaunchAgents/$LABEL.plist"

[ -f "$SRC" ] || { echo "missing $SRC" >&2; exit 1; }

# Replace USERNAME placeholder with the real $USER on the way in.
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
sed "s|/Users/USERNAME/|$HOME/|g" "$SRC" > "$DST"
chmod 0644 "$DST"

# Reload if already loaded.
if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
  echo "[install] bootout existing"
  launchctl bootout "gui/$(id -u)" "$DST" || true
fi
echo "[install] bootstrap"
launchctl bootstrap "gui/$(id -u)" "$DST"
echo "[install] enabled"
launchctl enable "gui/$(id -u)/$LABEL"

echo "[install] done — $LABEL will run daily."
echo "[install] kickstart now: launchctl kickstart -k gui/$(id -u)/$LABEL"
