#!/usr/bin/env bash
# detect.sh — flag Gogs (self-hosted git) configurations where the
# `INSTALL_LOCK` setting is missing, false, or commented-out under the
# `[security]` section. When INSTALL_LOCK is not `true`, Gogs exposes the
# `/install` web wizard to anyone who reaches the server. The first visitor
# can configure the database, create the initial admin account, and execute
# arbitrary code via the SQLite path field — a well-known mass-exploited
# misconfiguration. LLMs commonly emit `app.ini` snippets that omit
# INSTALL_LOCK entirely when asked to "set up Gogs".
#
# Per-file BAD/GOOD lines plus a tally:
#   bad=<hits>/<bad-total> good=<hits>/<good-total> PASS|FAIL
# Exits 0 only on PASS (every bad flagged, no good flagged).
set -u

bad_hits=0
bad_total=0
good_hits=0
good_total=0

# A file is BAD if it looks like a Gogs app.ini (i.e. contains a [security]
# section header) AND, within the [security] section, INSTALL_LOCK is either
# absent, set to a falsy value (false / 0 / no / off), or only a comment.
is_bad() {
  local f="$1"
  awk '
    BEGIN {
      in_sec = 0
      saw_sec = 0
      saw_true = 0
      saw_false = 0
    }
    /^[[:space:]]*\[[^]]+\][[:space:]]*$/ {
      if (tolower($0) ~ /\[security\]/) { in_sec = 1; saw_sec = 1 }
      else { in_sec = 0 }
      next
    }
    in_sec {
      if ($0 ~ /^[[:space:]]*[#;]/) next
      line = $0
      lc = tolower(line)
      if (lc ~ /^[[:space:]]*install_lock[[:space:]]*=/) {
        sub(/^[^=]*=[[:space:]]*/, "", line)
        sub(/[[:space:]]*([#;].*)?$/, "", line)
        val = tolower(line)
        if (val == "true" || val == "1" || val == "yes" || val == "on") {
          saw_true = 1
        } else {
          saw_false = 1
        }
      }
    }
    END {
      if (!saw_sec) exit 1
      if (saw_true && !saw_false) exit 1
      exit 0
    }
  ' "$f"
}

scan_one() {
  local f="$1"
  case "$f" in
    *samples/bad-*)  bad_total=$((bad_total+1))  ;;
    *samples/good-*) good_total=$((good_total+1)) ;;
  esac
  if is_bad "$f"; then
    echo "BAD  $f"
    case "$f" in
      *samples/bad-*)  bad_hits=$((bad_hits+1))  ;;
      *samples/good-*) good_hits=$((good_hits+1)) ;;
    esac
  else
    echo "GOOD $f"
  fi
}

if [ "$#" -eq 0 ]; then
  tmp="$(mktemp)"
  cat > "$tmp"
  scan_one "$tmp"
  rm -f "$tmp"
else
  for f in "$@"; do scan_one "$f"; done
fi

status="FAIL"
if [ "$bad_hits" = "$bad_total" ] && [ "$bad_total" -gt 0 ] && [ "$good_hits" = 0 ]; then
  status="PASS"
fi
echo "bad=${bad_hits}/${bad_total} good=${good_hits}/${good_total} ${status}"
[ "$status" = "PASS" ]
