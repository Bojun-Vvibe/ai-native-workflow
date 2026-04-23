#!/usr/bin/env bash
# notify-mac.sh — desktop banner via osascript. No third-party install.
#
# Usage: notify-mac.sh "<title>" "<body>"
#
# osascript's `display notification` is rate-limited by macOS; if you
# fire more than ~5 in a few seconds, some are dropped. This template
# only fires once per day, so that limit is irrelevant in normal use.

set -eu

title="${1:-anomaly-alert}"
body="${2:-(no body)}"

if ! command -v osascript >/dev/null 2>&1; then
  # Not on macOS; degrade to stderr.
  echo "[notify-mac] $title — $body" >&2
  exit 0
fi

# Escape double quotes in title/body before passing to AppleScript.
esc() { printf '%s' "$1" | sed 's/"/\\"/g'; }

osascript -e "display notification \"$(esc "$body")\" with title \"$(esc "$title")\""
