#!/usr/bin/env bash
# detect.sh — flag Gitea configs that leave INSTALL_LOCK off, exposing
# the first-run install wizard. See README.md for the rationale.
#
# Exit 0 iff every bad sample is flagged AND zero good samples are flagged.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

strip_comments() {
  # INI uses ';' and '#' for comments. YAML/Dockerfile use '#'.
  # Strip whole-line and trailing comments. Don't touch values that
  # contain '#' inside quotes — Gitea config values rarely do, and
  # the cost of being conservative is a missed false-positive only.
  sed -E -e 's/^[[:space:]]*[#;].*$//' -e 's/[[:space:]]+[#;].*$//' "$1"
}

is_gitea_config() {
  local s="$1"
  # Image / project hints
  printf '%s\n' "$s" | grep -Eiq '(^|[^a-z0-9_])gitea/gitea([^a-z0-9_]|$)' && return 0
  printf '%s\n' "$s" | grep -Eiq 'docs\.gitea\.(io|com)' && return 0
  # Env-var form is unambiguous
  printf '%s\n' "$s" | grep -Eiq 'GITEA__[A-Z0-9_]+' && return 0
  # INI form: a Gitea-specific key inside a recognizable section
  printf '%s\n' "$s" | grep -Eiq '^[[:space:]]*APP_NAME[[:space:]]*=' && return 0
  printf '%s\n' "$s" | grep -Eiq '^[[:space:]]*RUN_MODE[[:space:]]*=' \
    && printf '%s\n' "$s" | grep -Eiq '^[[:space:]]*RUN_USER[[:space:]]*=' && return 0
  # [server] + ROOT_URL/DOMAIN combo is a strong Gitea fingerprint
  if printf '%s\n' "$s" | grep -Eiq '^\[server\]'; then
    printf '%s\n' "$s" | grep -Eiq '^[[:space:]]*(ROOT_URL|DOMAIN|HTTP_PORT|SSH_PORT)[[:space:]]*=' && return 0
  fi
  return 1
}

# Return 0 (true) if a positive INSTALL_LOCK is set anywhere.
has_lock_true() {
  local s="$1"
  # INI: INSTALL_LOCK = true | 1 | yes | on (case-insensitive, optional quotes)
  printf '%s\n' "$s" \
    | grep -Eiq '^[[:space:]]*INSTALL_LOCK[[:space:]]*=[[:space:]]*"?(true|1|yes|on)"?[[:space:]]*$' \
    && return 0
  # Env-var form
  printf '%s\n' "$s" \
    | grep -Eiq '(^|[[:space:]"'\''])GITEA__SECURITY__INSTALL_LOCK[[:space:]]*[=:][[:space:]]*"?(true|1|yes|on)"?' \
    && return 0
  return 1
}

# Return 0 (true) if a negative INSTALL_LOCK is set anywhere.
has_lock_false() {
  local s="$1"
  printf '%s\n' "$s" \
    | grep -Eiq '^[[:space:]]*INSTALL_LOCK[[:space:]]*=[[:space:]]*"?(false|0|no|off)"?[[:space:]]*$' \
    && return 0
  printf '%s\n' "$s" \
    | grep -Eiq '(^|[[:space:]"'\''])GITEA__SECURITY__INSTALL_LOCK[[:space:]]*[=:][[:space:]]*"?(false|0|no|off)"?' \
    && return 0
  return 1
}

has_security_section() {
  printf '%s\n' "$1" | grep -Eiq '^\[security\]'
}

# Does the snippet set ANY Gitea env var (besides the lock itself)?
has_other_gitea_env() {
  printf '%s\n' "$1" \
    | grep -Eo 'GITEA__[A-Za-z0-9_]+' \
    | grep -Eiv '^GITEA__SECURITY__INSTALL_LOCK$' \
    | grep -q .
}

# Does the snippet appear to *configure* Gitea (vs. merely reference
# the image)? Used to suppress false positives on bare `image:` lines.
configures_gitea() {
  local s="$1"
  has_security_section "$s" && return 0
  printf '%s\n' "$s" | grep -Eiq '^\[(server|database|repository|service|log|mailer)\]' && return 0
  has_other_gitea_env "$s" && return 0
  printf '%s\n' "$s" | grep -Eiq '^[[:space:]]*APP_NAME[[:space:]]*=' && return 0
  return 1
}

is_bad_file() {
  local f="$1"
  local stripped
  stripped="$(strip_comments "$f")"

  is_gitea_config "$stripped" || return 1
  configures_gitea "$stripped" || return 1

  # Pattern 2/3: explicit false anywhere → bad.
  if has_lock_false "$stripped"; then return 0; fi

  # Pattern 1/4: lock not set to true.
  if ! has_lock_true "$stripped"; then return 0; fi

  return 1
}

for f in "$@"; do
  case "$f" in
    *samples/bad/*) bad_total=$((bad_total+1)) ;;
    *samples/good/*) good_total=$((good_total+1)) ;;
  esac
  if is_bad_file "$f"; then
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
