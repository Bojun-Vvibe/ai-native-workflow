#!/usr/bin/env bash
# detect.sh — flag Kubernetes manifests that publicly expose the Kubeflow
# central dashboard via an Istio AuthorizationPolicy with action: ALLOW and
# an empty (or missing) rules: block. Per Istio docs, an ALLOW policy with
# no rules matches everything; combined with a public kubeflow-gateway it
# leaves the notebook / pipelines / experiments UI browseable to anyone.
#
# Per-file BAD/GOOD lines plus a tally:
#   bad=<hits>/<bad-total> good=<hits>/<good-total> PASS|FAIL
# Exits 0 only on PASS.
set -u

bad_hits=0
bad_total=0
good_hits=0
good_total=0

is_bad() {
  local f="$1"
  awk '
    BEGIN {
      is_kf = 0
      is_authz = 0
      action = ""
      rules_seen = 0
      rules_real_entry = 0
      in_rules = 0
      rules_indent = -1
    }
    {
      raw = $0
      # Strip trailing CR.
      sub(/\r$/, "", raw)
      lower = tolower(raw)

      # Kubeflow heuristic: mentions kubeflow or centraldashboard anywhere.
      if (lower ~ /kubeflow/ || lower ~ /centraldashboard/) is_kf = 1

      if (lower ~ /^[[:space:]]*kind:[[:space:]]*authorizationpolicy[[:space:]]*$/) is_authz = 1

      # Capture action: value (last non-comment occurrence wins).
      if (raw ~ /^[[:space:]]*action:[[:space:]]*[A-Za-z]+/) {
        a = raw
        sub(/^[[:space:]]*action:[[:space:]]*/, "", a)
        sub(/[[:space:]]*([#].*)?$/, "", a)
        action = toupper(a)
      }

      # Detect entry into a rules: block.
      if (raw ~ /^[[:space:]]*rules:[[:space:]]*(\[\][[:space:]]*)?(#.*)?$/) {
        rules_seen = 1
        # Determine indentation of the "rules:" key.
        match(raw, /[^[:space:]]/)
        rules_indent = RSTART - 1
        in_rules = 1
        # If literal "rules: []" — no entries.
        if (raw ~ /rules:[[:space:]]*\[\]/) { in_rules = 0 }
        next
      }

      if (in_rules) {
        # Blank line — still inside block.
        if (raw ~ /^[[:space:]]*$/) next
        # Comment line — ignored, still inside block.
        if (raw ~ /^[[:space:]]*#/) next

        # Find indent of this content line.
        match(raw, /[^[:space:]]/)
        cur_indent = RSTART - 1

        if (cur_indent <= rules_indent) {
          # Left the rules block without finding a real list entry.
          in_rules = 0
        } else {
          # A line that is a YAML list entry under rules: counts as a real entry.
          # Real Istio rule entries start with "- from:" / "- to:" / "- when:".
          if (raw ~ /^[[:space:]]*-[[:space:]]*(from|to|when)[[:space:]]*:/) {
            rules_real_entry = 1
            in_rules = 0
          }
        }
      }
    }
    END {
      if (!is_kf || !is_authz) exit 1            # Not Kubeflow / not an AuthorizationPolicy: ignore.
      if (action != "ALLOW") exit 1               # DENY or unspecified: not flagged here.
      if (rules_real_entry) exit 1                # Real rule entry: GOOD.
      exit 0                                      # ALLOW + no real rules: BAD.
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
