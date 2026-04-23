#!/usr/bin/env bash
# run-anomaly-check.sh
#
# Runs an anomaly check and a budget check, deduplicates per-day,
# and dispatches notifications only when something is actually
# worth a human's attention.
#
# Exit codes:
#   0 — checks ran, nothing to alert about
#   1 — operational error (CLI missing, state dir unwritable, etc.)
#   2 — alert fired (or was deduplicated for today)
#
# Adapt the CLI_BIN / *_ARGS / NOTIFIERS variables at the top.

set -u
# Note: deliberately NOT `set -e`. We want to capture and route
# non-zero exits from the underlying CLI as signal, not as failure.

# --------- Adapt these ---------
CLI_BIN="${CLI_BIN:-pew}"
ANOMALY_ARGS=(anomalies --baseline 7d --lookback 30d --threshold 2.0)
BUDGET_ARGS=(budget --check --period day --ceiling 50000)
# Comma-separated list. Allowed values: mac, webhook
NOTIFIERS="${NOTIFIERS:-mac}"
# --------------------------------

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/anomaly-alert"
STATE_FILE="$STATE_DIR/last.json"
AUDIT_LOG="$STATE_DIR/audit.log"

mkdir -p "$STATE_DIR" || {
  echo "anomaly-alert: cannot create state dir $STATE_DIR" >&2
  exit 1
}

if ! command -v "$CLI_BIN" >/dev/null 2>&1; then
  echo "anomaly-alert: CLI_BIN '$CLI_BIN' not on PATH" >&2
  exit 1
fi

today="$(date +%Y-%m-%d)"
ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ---- Run checks. Capture exit codes; do not propagate. ----
"$CLI_BIN" "${ANOMALY_ARGS[@]}" >/dev/null 2>&1
anomaly_rc=$?
"$CLI_BIN" "${BUDGET_ARGS[@]}" >/dev/null 2>&1
budget_rc=$?

# By convention: rc==2 means "signal" (anomaly detected /
# budget breached); rc==0 means "all clear"; anything else is
# operational and we report it but do not page on it.
keys=()
[ "$anomaly_rc" = "2" ] && keys+=("anomaly")
[ "$budget_rc"  = "2" ] && keys+=("budget")

if [ "$anomaly_rc" != "0" ] && [ "$anomaly_rc" != "2" ]; then
  echo "$ts run rc=op-error step=anomaly cli_rc=$anomaly_rc" >> "$AUDIT_LOG"
fi
if [ "$budget_rc" != "0" ] && [ "$budget_rc" != "2" ]; then
  echo "$ts run rc=op-error step=budget cli_rc=$budget_rc" >> "$AUDIT_LOG"
fi

# Quiet day: nothing to do.
if [ "${#keys[@]}" -eq 0 ]; then
  echo "$ts run rc=quiet keys=" >> "$AUDIT_LOG"
  exit 0
fi

# ---- Deduplicate against state file. ----
already_alerted=""
if [ -f "$STATE_FILE" ]; then
  # Stdlib-only parse: read the file as plain text, look for today's date and the keys.
  prev_date="$(sed -n 's/.*"date"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$STATE_FILE" | head -n 1)"
  if [ "$prev_date" = "$today" ]; then
    prev_keys="$(sed -n 's/.*"keys_alerted"[[:space:]]*:[[:space:]]*\[\([^]]*\)\].*/\1/p' "$STATE_FILE" | head -n 1)"
    already_alerted="$prev_keys"
  fi
fi

new_keys=()
for k in "${keys[@]}"; do
  case "$already_alerted" in
    *"\"$k\""*) : ;;          # already alerted today, skip
    *)          new_keys+=("$k") ;;
  esac
done

if [ "${#new_keys[@]}" -eq 0 ]; then
  echo "$ts run rc=dedup keys=$(IFS=,; echo "${keys[*]}")" >> "$AUDIT_LOG"
  exit 2
fi

# ---- Build the alert payload. ----
title="anomaly-alert: $(IFS=,; echo "${new_keys[*]}") @ $today"
body="One or more checks fired:
- anomaly check rc=$anomaly_rc
- budget   check rc=$budget_rc
See $AUDIT_LOG for history."

# ---- Dispatch notifiers. ----
IFS=',' read -r -a notifier_list <<< "$NOTIFIERS"
for n in "${notifier_list[@]}"; do
  case "$n" in
    mac)     "$SCRIPT_DIR/notify-mac.sh"     "$title" "$body" || true ;;
    webhook) "$SCRIPT_DIR/notify-webhook.sh" "$title" "$body" || true ;;
    "")      : ;;
    *)       echo "$ts run rc=op-error unknown_notifier=$n" >> "$AUDIT_LOG" ;;
  esac
done

# ---- Update state file (combine today's accumulated keys). ----
combined_keys=()
for k in "${keys[@]}"; do combined_keys+=("\"$k\""); done
joined_keys="$(IFS=,; echo "${combined_keys[*]}")"
printf '{"date": "%s", "keys_alerted": [%s], "ts": "%s"}\n' \
  "$today" "$joined_keys" "$ts" > "$STATE_FILE"

echo "$ts run rc=alert keys=$(IFS=,; echo "${new_keys[*]}")" >> "$AUDIT_LOG"
exit 2
