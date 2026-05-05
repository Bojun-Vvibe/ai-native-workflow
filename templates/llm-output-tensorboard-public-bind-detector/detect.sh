#!/usr/bin/env bash
# detect.sh — flag shell scripts, Dockerfiles, and Compose snippets
# that start TensorBoard with the dashboard bound to every interface.
# TensorBoard ships with no authentication; binding it publicly
# exposes scalars, summaries, and the plugin file-fetch endpoints to
# anonymous visitors.
#
# Bad patterns we flag (line-oriented, see README for full rules):
#   1. `--bind_all` as a standalone token on a line that also
#      contains the bare token `tensorboard`.
#   2. `--host=0.0.0.0` (with or without surrounding quotes) on a
#      line that also contains `tensorboard`.
#   3. `--host 0.0.0.0` (space-separated form) on a line that also
#      contains `tensorboard`.
#
# Exit 0 iff every bad sample is flagged AND zero good samples are
# flagged.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

# Strip `#` line comments and inline `# ...` tails. We only honour
# `#` as a comment character when it is preceded by start-of-line or
# whitespace, so URLs containing `#` fragments are left intact. JSON-
# array Dockerfile CMD/ENTRYPOINT lines do not contain `#`, so the
# strip is safe for them too.
strip_comments() {
  sed -E -e 's/[[:space:]]+#.*$//' -e 's/^[[:space:]]*#.*$//' "$1"
}

# A line "mentions tensorboard" iff the bare token `tensorboard`
# appears with a word boundary on each side. We accept it inside
# JSON-array quoting (`"tensorboard"`), bare on a shell line, and
# after `python -m ` (where `tensorboard.main` matches via the
# leading `tensorboard` token).
mentions_tensorboard() {
  printf '%s\n' "$1" | grep -Eq '(^|[^[:alnum:]_.])tensorboard($|[^[:alnum:]_])'
}

# `--bind_all` as a standalone token. Surrounding chars must be
# whitespace, `=`, end-of-line, or quote.
match_bind_all() {
  printf '%s\n' "$1" | grep -Eq -e '(^|[[:space:]"'"'"'=,])--bind_all($|[[:space:]"'"'"'=,])'
}

# `--host=0.0.0.0` form (any quoting around the value).
match_host_eq_zero() {
  printf '%s\n' "$1" | grep -Eq -e '--host=("|'"'"')?0\.0\.0\.0("|'"'"')?($|[[:space:]"'"'"',])'
}

# `--host 0.0.0.0` space-separated form (any quoting around the
# value). We require at least one space between the flag and the
# value so we do not double-fire on the `=` form.
match_host_space_zero() {
  printf '%s\n' "$1" | grep -Eq -e '--host[[:space:]]+("|'"'"')?0\.0\.0\.0("|'"'"')?($|[[:space:]"'"'"',])'
}

is_bad() {
  local f="$1"
  local stripped tmp_line
  stripped="$(strip_comments "$f")"
  while IFS= read -r tmp_line; do
    [ -z "$tmp_line" ] && continue
    mentions_tensorboard "$tmp_line" || continue
    if match_bind_all "$tmp_line"; then return 0; fi
    if match_host_eq_zero "$tmp_line"; then return 0; fi
    if match_host_space_zero "$tmp_line"; then return 0; fi
  done <<< "$stripped"
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
