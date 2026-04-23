#!/usr/bin/env bash
# install.sh — symlink the plist into ~/Library/LaunchAgents/ and bootstrap.
set -eu

LABEL="${LABEL:-com.example.anomaly-alert-daily}"
SRC_PLIST="$(cd "$(dirname "$0")/../plist" && pwd)/$LABEL.plist"
DST_PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ ! -f "$SRC_PLIST" ]; then
  echo "install: plist not found at $SRC_PLIST" >&2
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"
ln -sfn "$SRC_PLIST" "$DST_PLIST"

# bootout silently if not loaded; bootstrap fresh.
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DST_PLIST"

echo "installed: $DST_PLIST -> $SRC_PLIST"
echo "verify:    launchctl print gui/\$(id -u)/$LABEL | head -30"
echo "force run: launchctl kickstart -k gui/\$(id -u)/$LABEL"
