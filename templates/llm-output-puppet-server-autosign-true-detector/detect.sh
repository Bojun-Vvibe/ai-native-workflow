#!/usr/bin/env bash
# detect.sh — flag Puppet master/server configs that turn on
# unconditional autosigning of agent certificates. Two physical
# files carry this knob:
#
#   1. `puppet.conf` (INI-style). The setting `autosign` lives under
#      `[master]`, `[server]`, or `[main]`. Truthy values that mean
#      "sign every CSR" are:
#         autosign = true
#         autosign = *
#      A path value (`autosign = /etc/puppetlabs/puppet/autosign.sh`)
#      is a *policy executable* and is safe — we do NOT flag it.
#      `autosign = false` is safe.
#
#   2. `autosign.conf` (filename literally ends `autosign.conf`).
#      A file whose only non-comment, non-blank entry is the bare
#      glob `*` is the equivalent of `autosign = true` — we flag it.
#      Specific hostnames or bounded suffixes (`*.nodes.internal.x`)
#      are fine.
#
# Comments (`#` and `;` to EOL) are stripped before evaluation.
# Exit 0 iff every bad sample is flagged AND zero good samples are flagged.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

strip_comments() {
  # puppet.conf accepts both `#` and `;` for comments. Strip both
  # full-line and trailing-after-whitespace forms.
  sed -E -e 's/[[:space:]]+[#;].*$//' -e 's/^[[:space:]]*[#;].*$//' "$1"
}

is_puppet_ini() {
  # Strong markers for puppet.conf: a [master|server|main|agent] section
  # header AND any puppet-flavoured key.
  local s="$1"
  printf '%s\n' "$s" | grep -Eiq '^[[:space:]]*\[(master|server|main|agent|user)\][[:space:]]*$' || return 1
  printf '%s\n' "$s" | grep -Eiq '^[[:space:]]*(autosign|certname|server|ca_server|environment|runinterval|report|reports|node_terminus|external_nodes|dns_alt_names)[[:space:]]*=' || return 1
  return 0
}

is_autosign_conf_filename() {
  case "$1" in
    *autosign.conf|*autosign.conf.example) return 0 ;;
    *) return 1 ;;
  esac
}

# value normaliser: strip whitespace, strip surrounding quotes,
# lowercase
norm_value() {
  printf '%s' "$1" \
    | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//' \
    | sed -E 's/^"(.*)"$/\1/; s/^'\''(.*)'\''$/\1/' \
    | tr 'A-Z' 'a-z'
}

scan_puppet_ini() {
  # Walk lines. Track current section. Flag any `autosign = <truthy>`
  # under [master]/[server]/[main]. Truthy = `true` or `*`.
  local stripped="$1"
  local section=""
  local flagged=1   # 1 == not flagged, shell-style
  while IFS= read -r line; do
    # section header?
    if [[ "$line" =~ ^[[:space:]]*\[([A-Za-z_]+)\][[:space:]]*$ ]]; then
      section="$(printf '%s' "${BASH_REMATCH[1]}" | tr 'A-Z' 'a-z')"
      continue
    fi
    # autosign assignment?
    if [[ "$line" =~ ^[[:space:]]*[Aa][Uu][Tt][Oo][Ss][Ii][Gg][Nn][[:space:]]*=[[:space:]]*(.*)$ ]]; then
      local raw="${BASH_REMATCH[1]}"
      local val
      val="$(norm_value "$raw")"
      case "$section" in
        master|server|main)
          case "$val" in
            true|"*")
              echo "  hit: [${section}] autosign = ${val}"
              flagged=0
              ;;
          esac
          ;;
      esac
    fi
  done <<<"$stripped"
  return $flagged
}

scan_autosign_conf() {
  # Flag iff there is a non-comment, non-blank line that is exactly
  # the bare glob `*` (with optional surrounding whitespace).
  local stripped="$1"
  local found_star=1
  while IFS= read -r line; do
    # skip blank
    [[ "$line" =~ ^[[:space:]]*$ ]] && continue
    # exact `*` after trim?
    local trimmed
    trimmed="$(printf '%s' "$line" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
    if [ "$trimmed" = "*" ]; then
      echo "  hit: autosign.conf bare wildcard line"
      found_star=0
    fi
  done <<<"$stripped"
  return $found_star
}

is_bad() {
  local f="$1"
  local stripped
  stripped="$(strip_comments "$f")"
  if is_autosign_conf_filename "$f"; then
    scan_autosign_conf "$stripped"
    return $?
  fi
  if is_puppet_ini "$stripped"; then
    scan_puppet_ini "$stripped"
    return $?
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
