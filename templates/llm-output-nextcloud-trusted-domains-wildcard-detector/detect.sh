#!/usr/bin/env bash
# detect.sh — flag Nextcloud `config.php` snippets where the
# `trusted_domains` array contains a wildcard entry (`*`), a glob like
# `*.example.com` / `something.*`, or the bind-everything sentinel
# `0.0.0.0`. Nextcloud uses `trusted_domains` as a host-header
# allowlist; if any entry matches everything, an attacker can serve
# the instance under an attacker-controlled hostname and pull off
# password-reset / OAuth-redirect / cache-poisoning attacks. LLMs
# frequently emit `'*'` "to make it work behind a reverse proxy".
#
# Per-file BAD/GOOD lines plus a tally:
#   bad=<hits>/<bad-total> good=<hits>/<good-total> PASS|FAIL
# Exits 0 only on PASS (every bad flagged, no good flagged).
set -u

bad_hits=0
bad_total=0
good_hits=0
good_total=0

# A file is BAD if it contains a `trusted_domains` PHP array assignment
# AND at least one quoted element inside that array value is a wildcard
# host: exactly `*`, contains an inner `*`, or is `0.0.0.0`.
is_bad() {
  local f="$1"
  awk '
    BEGIN {
      in_td   = 0
      depth   = 0
      opened  = 0
      saw_td  = 0
      bad     = 0
      SQ      = sprintf("%c", 39)   # single quote
      DQ      = sprintf("%c", 34)   # double quote
    }
    {
      line = $0
      lc   = tolower(line)

      # Enter trusted_domains value when we see the key + => on the line.
      if (!in_td) {
        if (lc ~ /["'\'']trusted_domains["'\'']/ && index(lc, "=>") > 0) {
          in_td   = 1
          saw_td  = 1
          # Trim everything up to and including the => so we only inspect
          # the value side from here onward.
          sub(/^.*=>[[:space:]]*/, "", line)
        } else {
          next
        }
      }

      # Track array bracket depth across the multi-line value.
      n_open  = gsub(/\[/, "[", line) + gsub(/[Aa][Rr][Rr][Aa][Yy]\(/, "&", line)
      n_close = gsub(/\]/, "]", line) + gsub(/\)/, ")", line)
      depth  += n_open - n_close
      if (n_open > 0) opened = 1

      # Walk the line, extracting each quoted string element.
      s = line
      while (1) {
        # Find the next quote of either flavour.
        pos_s = index(s, SQ)
        pos_d = index(s, DQ)
        if (pos_s == 0 && pos_d == 0) break
        if (pos_s == 0)      { q = DQ; pos = pos_d }
        else if (pos_d == 0) { q = SQ; pos = pos_s }
        else if (pos_s < pos_d) { q = SQ; pos = pos_s }
        else                 { q = DQ; pos = pos_d }

        rest = substr(s, pos + 1)
        end  = index(rest, q)
        if (end == 0) break
        elem = substr(rest, 1, end - 1)

        if (elem == "*" || elem == "0.0.0.0") { bad = 1 }
        else if (index(elem, "*") > 0)        { bad = 1 }

        s = substr(rest, end + 1)
      }

      if (opened && depth <= 0) { in_td = 0; opened = 0; depth = 0 }
    }
    END {
      if (!saw_td) exit 1
      if (bad)     exit 0
      exit 1
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
