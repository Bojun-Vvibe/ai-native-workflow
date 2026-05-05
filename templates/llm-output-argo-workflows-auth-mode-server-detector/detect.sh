#!/usr/bin/env bash
# detect.sh — flag Argo Workflows server configs that LLMs commonly
# emit with `--auth-mode=server` as the sole auth mode. The `server`
# mode tells the API server to act with the identity of its own
# ServiceAccount for every request, so any unauthenticated caller who
# can reach the API endpoint inherits the server's RBAC. The Argo
# Workflows docs explicitly warn that `server` mode "should not be used
# alone in shared or production clusters".
#
# Bad patterns we flag:
#   1. CLI flag `--auth-mode=server` (or `--auth-mode server`) with no
#      companion `--auth-mode=<other>` in the same file.
#   2. YAML scalar `mode: server` (under `auth:` or `extraArgs:`) with
#      no companion `mode:` setting a non-`server` value.
#   3. YAML list whose `mode:` block-scalar children are exactly the
#      single entry `server`.
#
# Exit 0 iff every bad sample is flagged AND zero good samples are
# flagged.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

strip_comments() {
  sed -E -e 's/[[:space:]]+#.*$//' -e 's/^[[:space:]]*#.*$//' "$1"
}

normalize() {
  # Strip quoting / brackets / commas so JSON-array args render as
  # plain whitespace-separated tokens, then collapse `=,` into `,`.
  printf '%s\n' "$1" | tr -d "\"'[]" | sed -E 's/,/ /g'
}

# Collect every `--auth-mode=<value>` (or `--auth-mode <value>`) token
# from the normalized stream. Comma-separated values are exploded so
# `--auth-mode=server,client` yields two tokens.
collect_cli_modes() {
  local n="$1"
  printf '%s\n' "$n" \
    | grep -Eo -- '--auth-mode[ =][a-zA-Z]+' \
    | sed -E 's/^--auth-mode[ =]//'
}

# Collect every `mode: <value>` scalar (single-line shape, NOT the
# block-list shape).
collect_yaml_scalar_modes() {
  local s="$1"
  # Match: optional indent, `mode:`, whitespace, value (letters only),
  # optional trailing whitespace. Excludes block-list openers
  # (`mode:` with no value on the same line).
  printf '%s\n' "$s" \
    | grep -Eo '^[[:space:]]*mode:[[:space:]]*[a-zA-Z]+[[:space:]]*$' \
    | sed -E 's/^[[:space:]]*mode:[[:space:]]*([a-zA-Z]+)[[:space:]]*$/\1/'
}

# Walk the YAML and collect the children of every `mode:` block-list
# (`mode:` alone on a line, followed by lines indented deeper that
# start with `- `). Print each collected list as a single
# space-separated line with a `LIST:` prefix.
collect_yaml_list_modes() {
  awk '
    function indent(s,   i) { i = match(s, /[^ ]/); return (i == 0 ? 0 : i - 1) }
    BEGIN { in_list=0; list_indent=-1; buf="" }
    {
      line=$0
      if (line ~ /^[[:space:]]*$/) next
      ind = indent(line)
      stripped = line
      sub(/^[[:space:]]+/, "", stripped)

      if (in_list && ind <= list_indent) {
        if (buf != "") print "LIST:" buf
        in_list=0; list_indent=-1; buf=""
      }

      if (!in_list && stripped ~ /^mode:[[:space:]]*$/) {
        in_list=1; list_indent=ind; buf=""; next
      }

      if (in_list && ind > list_indent && stripped ~ /^-[[:space:]]+[a-zA-Z]+[[:space:]]*$/) {
        val = stripped
        sub(/^-[[:space:]]+/, "", val)
        sub(/[[:space:]]+$/, "", val)
        buf = (buf == "" ? val : buf " " val)
      }
    }
    END { if (in_list && buf != "") print "LIST:" buf }
  ' <<<"$1"
}

is_bad() {
  local f="$1"
  local stripped normalized
  stripped="$(strip_comments "$f")"
  normalized="$(normalize "$stripped")"

  local cli_modes scalar_modes list_modes
  cli_modes="$(collect_cli_modes "$normalized")"
  scalar_modes="$(collect_yaml_scalar_modes "$stripped")"
  list_modes="$(collect_yaml_list_modes "$stripped")"

  # Rule 1: CLI flag form.
  if [ -n "$cli_modes" ]; then
    if printf '%s\n' "$cli_modes" | grep -qx 'server'; then
      # `server` is present; flag iff no non-`server` mode is also set.
      if ! printf '%s\n' "$cli_modes" | grep -vx 'server' | grep -q .; then
        return 0
      fi
    fi
  fi

  # Rule 2: YAML scalar form.
  if [ -n "$scalar_modes" ]; then
    if printf '%s\n' "$scalar_modes" | grep -qx 'server'; then
      if ! printf '%s\n' "$scalar_modes" | grep -vx 'server' | grep -q .; then
        # Make sure there is no companion CLI flag with a different mode.
        if [ -z "$cli_modes" ] || ! printf '%s\n' "$cli_modes" | grep -vx 'server' | grep -q .; then
          return 0
        fi
      fi
    fi
  fi

  # Rule 3: YAML list form.
  if [ -n "$list_modes" ]; then
    while IFS= read -r entry; do
      [ -z "$entry" ] && continue
      values="${entry#LIST:}"
      # Trim and check exact set == {server}.
      set -- $values
      if [ "$#" = 1 ] && [ "$1" = "server" ]; then
        return 0
      fi
    done <<<"$list_modes"
  fi

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
