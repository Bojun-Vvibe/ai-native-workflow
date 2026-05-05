#!/usr/bin/env bash
# detect.sh — flag Apache Solr `security.json` files whose
# `authentication` block configures one of Solr's built-in plugins
# but either sets `"blockUnknown": false` explicitly or omits the
# key entirely (Solr defaults to `false`). Either shape leaves the
# Solr admin/replication/collection APIs reachable without a
# password.
#
# Bad patterns we flag (line-oriented, see README for full rules):
#   1. A `"class": "solr.{Basic|JWT|PKI}AuthenticationPlugin"`
#      (or `BasicAuthPlugin` / `JWTAuthPlugin`) line with
#      `"blockUnknown": false` (any whitespace) within +/- 5 lines.
#   2. The same plugin class line with NO `blockUnknown` key in the
#      +/- 5 line window — Solr defaults that to `false`.
#
# Exit 0 iff every bad sample is flagged AND zero good samples are
# flagged.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

# Returns the 1-indexed line numbers of every line that declares a
# Solr authentication plugin class. We accept the three upstream
# plugin classes and tolerate single OR double quotes plus arbitrary
# whitespace around `:`.
plugin_lines() {
  grep -nE '"class"[[:space:]]*:[[:space:]]*"solr\.(BasicAuthPlugin|JWTAuthPlugin|PKIAuthenticationPlugin)"' "$1" \
    | cut -d: -f1
}

# Within the +/- 5 line window around $line in $file, is there a
# `"blockUnknown": true` setting? Returns 0 (true) iff yes.
window_has_blockunknown_true() {
  local file="$1" line="$2"
  local lo=$((line - 5)); [ "$lo" -lt 1 ] && lo=1
  local hi=$((line + 5))
  sed -n "${lo},${hi}p" "$file" \
    | grep -Eq '"blockUnknown"[[:space:]]*:[[:space:]]*true([[:space:]]*[,}]|[[:space:]]*$)'
}

# Within the +/- 5 line window around $line in $file, is there a
# `"blockUnknown": false` setting? Returns 0 (true) iff yes.
window_has_blockunknown_false() {
  local file="$1" line="$2"
  local lo=$((line - 5)); [ "$lo" -lt 1 ] && lo=1
  local hi=$((line + 5))
  sed -n "${lo},${hi}p" "$file" \
    | grep -Eq '"blockUnknown"[[:space:]]*:[[:space:]]*false([[:space:]]*[,}]|[[:space:]]*$)'
}

is_bad() {
  local f="$1"
  local lines
  lines="$(plugin_lines "$f")"
  [ -z "$lines" ] && return 1
  local ln
  while IFS= read -r ln; do
    [ -z "$ln" ] && continue
    if window_has_blockunknown_false "$f" "$ln"; then
      return 0
    fi
    if ! window_has_blockunknown_true "$f" "$ln"; then
      # Plugin declared, no `blockUnknown: true` nearby → defaults to
      # false → bad.
      return 0
    fi
  done <<< "$lines"
  return 1
}

for f in "$@"; do
  case "$f" in
    *samples/bad/*) bad_total=$((bad_total+1)) ;;
    *samples/good/*) good_total=$((good_total+1)) ;;
  esac
  if is_bad "$f"; then
    echo "BAD  $f"
    case "$f" in
      *samples/bad/*) bad_hits=$((bad_hits+1)) ;;
      *samples/good/*) good_hits=$((good_hits+1)) ;;
    esac
  else
    echo "GOOD $f"
  fi
done

status="FAIL"
if [ "$bad_hits" = "$bad_total" ] && [ "$good_hits" = 0 ]; then
  status="PASS"
fi
echo "bad=${bad_hits}/${bad_total} good=${good_hits}/${good_total} ${status}"
[ "$status" = "PASS" ]
