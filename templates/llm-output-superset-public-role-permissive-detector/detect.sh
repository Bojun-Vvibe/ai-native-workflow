#!/usr/bin/env bash
# detect.sh — flag Apache Superset `superset_config.py` files that
# bind the built-in `Public` role to a non-empty source role via
# `PUBLIC_ROLE_LIKE` (or the legacy `PUBLIC_ROLE_LIKE_GAMMA = True`
# boolean). Either knob causes Superset's `init` command to copy the
# source role's permissions onto `Public`, which means every
# anonymous visitor of the UI / SQL Lab / charts API inherits those
# permissions.
#
# Bad patterns we flag:
#   1. PUBLIC_ROLE_LIKE = "<non-empty literal>" (single or double
#      quoted, value not `None`).
#   2. PUBLIC_ROLE_LIKE = os.environ.get("...", "<non-empty literal>")
#      (or os.getenv(...) with the same shape).
#   3. PUBLIC_ROLE_LIKE_GAMMA = True.
#
# Exit 0 iff every bad sample is flagged AND zero good samples are
# flagged.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

strip_comments() {
  # Python uses `#` for comments. Strip leading-`#` lines and inline
  # `# ...` tails. Be conservative about `#` inside string literals:
  # the rules below only fire on assignment shapes whose RHS is a
  # quoted string or a True/False literal, neither of which contains
  # an unescaped `#` in any of our match patterns, so a naive strip
  # is safe here.
  sed -E -e 's/[[:space:]]+#.*$//' -e 's/^[[:space:]]*#.*$//' "$1"
}

# Rule 1 — direct assignment to a non-empty quoted string literal that
# is not the bare word `None`. We require at least one non-quote
# character between the quotes.
match_direct_string() {
  local s="$1"
  printf '%s\n' "$s" | grep -Eq \
    '^[[:space:]]*PUBLIC_ROLE_LIKE[[:space:]]*=[[:space:]]*("[^"]+"|'"'"'[^'"'"']+'"'"')[[:space:]]*$'
}

# Rule 2 — assignment via os.environ.get(KEY, "<default>") or
# os.getenv(KEY, "<default>") where the default is a non-empty quoted
# string literal.
match_env_default() {
  local s="$1"
  printf '%s\n' "$s" | grep -Eq \
    '^[[:space:]]*PUBLIC_ROLE_LIKE[[:space:]]*=[[:space:]]*os\.(environ\.get|getenv)\([^,]+,[[:space:]]*("[^"]+"|'"'"'[^'"'"']+'"'"')[[:space:]]*\)[[:space:]]*$'
}

# Rule 3 — legacy boolean knob set to True.
match_legacy_gamma_true() {
  local s="$1"
  printf '%s\n' "$s" | grep -Eq \
    '^[[:space:]]*PUBLIC_ROLE_LIKE_GAMMA[[:space:]]*=[[:space:]]*True[[:space:]]*$'
}

is_bad() {
  local f="$1"
  local stripped
  stripped="$(strip_comments "$f")"

  if match_direct_string "$stripped"; then return 0; fi
  if match_env_default "$stripped"; then return 0; fi
  if match_legacy_gamma_true "$stripped"; then return 0; fi
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
