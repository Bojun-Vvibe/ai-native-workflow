#!/usr/bin/env bash
# notify-webhook.sh — POSTs a JSON payload to a webhook URL.
#
# Usage: notify-webhook.sh "<title>" "<body>"
#
# Reads the webhook URL from $WEBHOOK_FILE (default
# ~/.config/anomaly-alert/webhook). The file must:
#   - exist
#   - be a regular file
#   - have permissions 600 (owner read/write only)
#
# Refusing to read a world-readable webhook file is intentional:
# the URL is a credential. If you control posting permission to a
# Slack channel, that URL is enough to spam it.

set -eu

title="${1:-anomaly-alert}"
body="${2:-(no body)}"

WEBHOOK_FILE="${WEBHOOK_FILE:-$HOME/.config/anomaly-alert/webhook}"

if [ ! -f "$WEBHOOK_FILE" ]; then
  # Not configured. Silent no-op (the wrapper logs the dispatch attempt).
  exit 0
fi

# Permission check: must be 600 (or 400). Anything more permissive aborts.
perms="$(stat -f '%A' "$WEBHOOK_FILE" 2>/dev/null || stat -c '%a' "$WEBHOOK_FILE" 2>/dev/null || echo "")"
case "$perms" in
  600|400) : ;;
  *)
    echo "notify-webhook: refusing — $WEBHOOK_FILE has perms $perms (want 600)" >&2
    exit 1
  ;;
esac

url="$(head -n 1 "$WEBHOOK_FILE" | tr -d '[:space:]')"
if [ -z "$url" ]; then
  echo "notify-webhook: $WEBHOOK_FILE is empty" >&2
  exit 1
fi

# Build a minimal JSON payload. Caller is responsible for higher-level
# routing (Slack vs Discord vs PagerDuty); the body field is the
# common denominator most webhook receivers accept.
escape_json() {
  python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"
}
title_json="$(escape_json "$title")"
body_json="$(escape_json "$body")"
payload="{\"text\": $title_json, \"body\": $body_json}"

# --max-time prevents a hung notifier from blocking the next run.
# --fail makes curl exit non-zero on HTTP >=400 so the wrapper logs it.
curl --silent --show-error --fail --max-time 10 \
  -H 'Content-Type: application/json' \
  -X POST \
  --data "$payload" \
  "$url" >/dev/null
