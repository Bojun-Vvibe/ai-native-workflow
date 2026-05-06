#!/usr/bin/env bash
# detect.sh — flag Knot DNS server configurations that LLMs
# routinely emit with an `acl:` entry permitting the `update`
# action (RFC 2136 dynamic DNS) from any source address. Knot DNS
# uses a YAML-style configuration. An ACL that lists
# `action: update` AND either omits `address:` entirely or sets it
# to `0.0.0.0/0` / `::/0` lets anyone on the internet rewrite the
# zone, which is functionally equivalent to handing out the zone
# signing key.
#
# Bad patterns (any one is sufficient):
#   1. A YAML `acl:` list element with `action: update` (or an
#      `action: [..., update, ...]` sequence) and NO `address:`
#      key in the same element.
#   2. A YAML `acl:` list element with `action: update` (in any
#      form) and `address: 0.0.0.0/0` (or `::/0`, or the bare
#      keyword `any`).
#   3. The same shape expressed via `actions: update` (Knot
#      historically accepted both spellings in user-facing docs
#      and many LLM templates use the plural).
#
# Good patterns are the inverse: ACLs that grant `update` only to
# a concrete non-default CIDR, or ACLs that grant only
# `transfer` / `notify`, or ACLs gated on a TSIG `key:` reference.
#
# Exit 0 iff every bad sample is flagged AND zero good samples are flagged.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

strip_comments() {
  # Knot uses YAML; strip `#` line comments.
  sed -E -e 's/[[:space:]]+#.*$//' -e 's/^[[:space:]]*#.*$//' "$1"
}

is_knot_config() {
  local s="$1"
  # Knot YAML markers: a top-level `acl:` block, or `zone:` /
  # `template:` sections, or `server:` with `listen:` keys typical
  # of Knot. We require an `acl:` block to even consider this file
  # in scope.
  printf '%s\n' "$s" | grep -Eq '^[[:space:]]*acl:[[:space:]]*$' || return 1
  printf '%s\n' "$s" \
    | grep -Eq '^[[:space:]]*(zone|template|server|remote|key):[[:space:]]*$' \
    && return 0
  # An acl block alone with action/address keys is enough.
  printf '%s\n' "$s" \
    | grep -Eq '^[[:space:]]*-[[:space:]]*id:[[:space:]]*' \
    && return 0
  return 1
}

# Walk the acl: block and emit each list-item record as a single
# line of `key=value;key=value;...` so we can reason about each
# entry independently. We only support the small subset of YAML
# Knot actually uses (block-style mapping under a sequence).
extract_acl_items() {
  awk '
    BEGIN { in_acl=0; in_item=0; rec="" }
    function flush() {
      if (in_item && rec != "") { print rec }
      rec=""; in_item=0
    }
    # Detect entering / leaving the acl: block.
    /^[[:space:]]*acl:[[:space:]]*$/ { flush(); in_acl=1; next }
    # A new top-level section ends the acl block.
    in_acl && /^[A-Za-z_][A-Za-z0-9_-]*:[[:space:]]*$/ { flush(); in_acl=0 }
    !in_acl { next }

    # New list item starts with `- id:` (or `- key:` etc).
    /^[[:space:]]*-[[:space:]]+[A-Za-z_][A-Za-z0-9_-]*:/ {
      flush()
      in_item=1
      line=$0
      sub(/^[[:space:]]*-[[:space:]]+/, "", line)
      # line is now `key: value` (or `key:` with no value)
      key=line; val=line
      sub(/:.*$/, "", key)
      sub(/^[^:]*:[[:space:]]*/, "", val)
      rec=key "=" val
      next
    }
    # Continuation key inside the current item (deeper indent).
    in_item && /^[[:space:]]+[A-Za-z_][A-Za-z0-9_-]*:/ {
      line=$0
      sub(/^[[:space:]]+/, "", line)
      key=line; val=line
      sub(/:.*$/, "", key)
      sub(/^[^:]*:[[:space:]]*/, "", val)
      rec=rec ";" key "=" val
      next
    }
    END { flush() }
  ' <<< "$1"
}

item_action_has_update() {
  local rec="$1"
  # Pull out action= or actions= value (rest of line up to next ;)
  local a
  a="$(printf '%s\n' "$rec" \
        | tr ';' '\n' \
        | grep -E '^(action|actions)=' \
        | head -n1 \
        | sed -E 's/^[^=]*=//')"
  [ -n "$a" ] || return 1
  # Strip surrounding [ ] and quotes, lowercase.
  a="$(printf '%s' "$a" | tr 'A-Z' 'a-z' \
        | sed -E -e 's/^[[:space:]]*\[//' -e 's/\][[:space:]]*$//' \
                 -e 's/"//g' -e "s/'//g")"
  # Tokenize on commas / whitespace and match `update` exactly.
  printf '%s\n' "$a" | tr ', ' '\n\n' | grep -Fxq update
}

item_address_value() {
  local rec="$1"
  printf '%s\n' "$rec" \
    | tr ';' '\n' \
    | grep -E '^address=' \
    | head -n1 \
    | sed -E 's/^[^=]*=//' \
    | sed -E -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \
    | sed -E -e 's/^"(.*)"$/\1/' -e "s/^'(.*)'\$/\1/"
}

address_is_anywhere() {
  local v="$1"
  case "$v" in
    "0.0.0.0/0"|"::/0"|"any"|"ANY"|"Any") return 0 ;;
    *) return 1 ;;
  esac
}

is_bad_acl() {
  local items
  items="$(extract_acl_items "$1")"
  [ -n "$items" ] || return 1
  local rec addr
  while IFS= read -r rec; do
    [ -n "$rec" ] || continue
    item_action_has_update "$rec" || continue
    addr="$(item_address_value "$rec")"
    if [ -z "$addr" ]; then
      # `update` granted with no address: → bad.
      return 0
    fi
    if address_is_anywhere "$addr"; then
      return 0
    fi
  done <<< "$items"
  return 1
}

is_bad() {
  local f="$1"
  local stripped
  stripped="$(strip_comments "$f")"
  is_knot_config "$stripped" || return 1
  is_bad_acl "$stripped"
}

for f in "$@"; do
  case "$f" in
    *samples/bad/*)  bad_total=$((bad_total+1)) ;;
    *samples/good/*) good_total=$((good_total+1)) ;;
  esac
  if is_bad "$f"; then
    echo "BAD  $f"
    case "$f" in
      *samples/bad/*)  bad_hits=$((bad_hits+1)) ;;
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
