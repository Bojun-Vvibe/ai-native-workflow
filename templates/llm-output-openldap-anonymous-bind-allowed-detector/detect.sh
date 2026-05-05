#!/usr/bin/env bash
# detect.sh — flag OpenLDAP (slapd) configurations that LLMs commonly emit
# without disabling anonymous binds. Out of the box, slapd permits anonymous
# bind (an empty DN with empty password) which lets unauthenticated clients
# enumerate the directory tree via a simple `ldapsearch -x -H ldap://host
# -b <base>`. The hardening knobs are:
#
#   * Legacy `slapd.conf` form: a top-level `disallow bind_anon` line.
#   * cn=config (OLC) form: an `olcDisallows: bind_anon` attribute on the
#     `cn=config` (or frontend) entry, OR `olcRequires: authc` on the
#     database / frontend entry.
#   * Invocation form: `slapd ... -o disallow=bind_anon ...`.
#
# When LLMs are asked "set up an OpenLDAP server with users and groups",
# they routinely emit a working slapd config that omits all of the above,
# leaving the directory readable to anyone on the network.
#
# Bad patterns we flag:
#   1. `slapd.conf` (or anything containing `database`, `suffix`,
#      `rootdn`, `access to`) with NO `disallow bind_anon` AND NO
#      `require authc` line.
#   2. cn=config LDIF (anything with `dn: cn=config`, `olcDatabase`,
#      `olcSuffix`, `olcRootDN`) with NO `olcDisallows: bind_anon` AND
#      NO `olcRequires: authc`.
#   3. Compose / Dockerfile / shell invocation of `slapd` with no
#      `-o disallow=bind_anon` and no referenced config that would
#      supply it (we only flag if we can see the invocation but not a
#      `-f` / `-F` pointing at an external file).
#
# Exit 0 iff every bad sample is flagged AND zero good samples are flagged.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

strip_comments() {
  # slapd.conf uses `#` line comments. LDIF treats `#` only at column 0 as a
  # comment; we strip both forms conservatively.
  sed -E -e 's/^[[:space:]]*#.*$//' "$1"
}

is_slapd_conf_file() {
  local s="$1"
  printf '%s\n' "$s" | grep -Eiq '(^|[^[:alnum:]_-])(database[[:space:]]+(mdb|hdb|bdb|ldif|monitor)|^[[:space:]]*suffix[[:space:]]+"|^[[:space:]]*rootdn[[:space:]]+"|^[[:space:]]*access[[:space:]]+to[[:space:]])'
}

is_olc_ldif_file() {
  local s="$1"
  printf '%s\n' "$s" | grep -Eiq '(^|\n)dn:[[:space:]]*(cn=config|olcDatabase=|cn=schema,cn=config)' \
    || printf '%s\n' "$s" | grep -Eiq '^[[:space:]]*olc(Database|Suffix|RootDN|RootPW|Access):'
}

is_slapd_invocation() {
  local s="$1"
  printf '%s\n' "$s" | grep -Eiq '(^|[[:space:]/"])slapd\b'
}

has_slapd_conf_disallow() {
  printf '%s\n' "$1" | grep -Eiq '^[[:space:]]*disallow[[:space:]]+([^#]*[[:space:]])?bind_anon\b'
}

has_slapd_conf_require_authc() {
  # `require authc` (or `require strong`/`SASL`) on a database/global block
  # forces a real bind before any operation.
  printf '%s\n' "$1" | grep -Eiq '^[[:space:]]*require[[:space:]]+([^#]*[[:space:]])?(authc|strong|sasl)\b'
}

has_olc_disallow_bind_anon() {
  printf '%s\n' "$1" | grep -Eiq '^[[:space:]]*olcDisallows:[[:space:]]+([^#]*[[:space:]])?bind_anon\b'
}

has_olc_requires_authc() {
  printf '%s\n' "$1" | grep -Eiq '^[[:space:]]*olcRequires:[[:space:]]+([^#]*[[:space:]])?(authc|strong|sasl)\b'
}

invocation_has_disallow_bind_anon() {
  # Tolerate JSON-array CMD splitting and quoting noise.
  local normalized
  normalized="$(printf '%s\n' "$1" | tr -d '",[]')"
  printf '%s\n' "$normalized" \
    | grep -Eiq '(^|[[:space:]])-o[[:space:]]+disallow=([^[:space:]]*,)?bind_anon\b'
}

invocation_references_external_config() {
  # `-f /etc/openldap/slapd.conf` or `-F /etc/openldap/slapd.d` means the
  # invocation alone cannot tell us whether bind_anon is disabled — defer
  # to the file-based rules and do not flag the invocation itself.
  local normalized
  normalized="$(printf '%s\n' "$1" | tr -d '",[]')"
  printf '%s\n' "$normalized" | grep -Eiq '(^|[[:space:]])-(f|F)[[:space:]]+[^[:space:]]+'
}

is_bad() {
  local f="$1"
  local stripped
  stripped="$(strip_comments "$f")"

  # Rule 3 — invocation only. We only fire this rule when the file is
  # *purely* an invocation (Dockerfile / compose snippet / shell script)
  # without any embedded slapd directive content.
  if is_slapd_invocation "$stripped" \
     && ! is_slapd_conf_file "$stripped" \
     && ! is_olc_ldif_file "$stripped"; then
    if ! invocation_has_disallow_bind_anon "$stripped" \
       && ! invocation_references_external_config "$stripped"; then
      return 0
    fi
    return 1
  fi

  # Rule 2 — cn=config / OLC LDIF.
  if is_olc_ldif_file "$stripped"; then
    if ! has_olc_disallow_bind_anon "$stripped" \
       && ! has_olc_requires_authc "$stripped"; then
      return 0
    fi
    return 1
  fi

  # Rule 1 — legacy slapd.conf.
  if is_slapd_conf_file "$stripped"; then
    if ! has_slapd_conf_disallow "$stripped" \
       && ! has_slapd_conf_require_authc "$stripped"; then
      return 0
    fi
    return 1
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
