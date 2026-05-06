#!/usr/bin/env bash
# detect.sh — flag SFTPGo configurations that LLMs routinely emit
# with default / placeholder admin credentials. SFTPGo is a
# self-hosted SFTP/HTTP/WebDAV file server whose WebAdmin UI grants
# full filesystem + user administration. With first-run defaults
# baked in (admin/password), any reachable WebAdmin port becomes a
# remote root-equivalent.
#
# Bad patterns (any one is sufficient):
#   1. SFTPGo JSON/YAML config with create_default_admin=true AND
#      default_admin_password unset or in the placeholder set.
#   2. Docker / systemd / .env file exporting
#      SFTPGO_DATA_PROVIDER__CREATE_DEFAULT_ADMIN truthy AND
#      SFTPGO_DATA_PROVIDER__DEFAULT_ADMIN_PASSWORD missing or in
#      the placeholder set.
#   3. SFTPGo config/env where the username AND password are both
#      placeholders.
#
# Good patterns are the inverse: create_default_admin=false, OR a
# non-placeholder password (long random / secret-ref).
#
# Exit 0 iff every bad sample is flagged AND zero good samples are flagged.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

strip_comments() {
  # JSON technically has no comments but SFTPGo accepts JSONC. Also
  # handle YAML / .env / shell.
  sed -E -e 's@[[:space:]]+//.*$@@' -e 's@^[[:space:]]*//.*$@@' \
         -e 's/[[:space:]]+#.*$//' -e 's/^[[:space:]]*#.*$//' "$1"
}

is_sftpgo_config() {
  local s="$1"
  # JSON/YAML config marker: a `data_provider` key, OR top-level
  # SFTPGo-shaped keys (sftpd, httpd, webdavd) plus any
  # default_admin_* / create_default_admin reference.
  printf '%s\n' "$s" | grep -Eq '"?(data_provider|sftpd|httpd|webdavd)"?[[:space:]]*:' \
    || return 1
  printf '%s\n' "$s" | grep -Eq '"?(create_default_admin|default_admin_username|default_admin_password)"?[[:space:]]*:' \
    || return 1
  return 0
}

is_sftpgo_env() {
  local s="$1"
  printf '%s\n' "$s" | grep -Eq 'SFTPGO_DATA_PROVIDER__(CREATE_DEFAULT_ADMIN|DEFAULT_ADMIN_USERNAME|DEFAULT_ADMIN_PASSWORD)\b'
}

config_create_default_admin_true() {
  local s="$1"
  printf '%s\n' "$s" \
    | grep -Eq '"?create_default_admin"?[[:space:]]*:[[:space:]]*(true|"true"|1|"1"|yes|"yes")'
}

# Pull the value of a JSON/YAML key like default_admin_password.
config_get_value() {
  local s="$1" key="$2"
  printf '%s\n' "$s" \
    | grep -E "\"?${key}\"?[[:space:]]*:" \
    | head -n1 \
    | sed -E "s/.*\"?${key}\"?[[:space:]]*:[[:space:]]*//" \
    | sed -E 's/,[[:space:]]*$//' \
    | sed -E 's/^"(.*)"$/\1/' \
    | sed -E "s/^'(.*)'\$/\1/" \
    | sed -E 's/[[:space:]]+$//'
}

# Pull the value of an env var assignment.
env_get_value() {
  local s="$1" key="$2"
  printf '%s\n' "$s" \
    | grep -E "(^|[[:space:]]|^export[[:space:]]+|^[A-Z0-9_]+=)${key}=" \
    | head -n1 \
    | sed -E "s/.*${key}=//" \
    | sed -E 's/[[:space:]].*$//' \
    | sed -E 's/^"(.*)"$/\1/' \
    | sed -E "s/^'(.*)'\$/\1/"
}

is_placeholder() {
  local v
  v="$(printf '%s' "$1" | tr 'A-Z' 'a-z')"
  case "$v" in
    ""|password|admin|sftpgo|root|changeme|change_me|please_change_me|please-change-me|secret|defaultpassword|default_password|your_password|your-password) return 0 ;;
    *) return 1 ;;
  esac
}

env_truthy() {
  local v
  v="$(printf '%s' "$1" | tr 'A-Z' 'a-z')"
  case "$v" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

is_bad_config() {
  local s="$1"
  is_sftpgo_config "$s" || return 1
  config_create_default_admin_true "$s" || return 1

  local pw
  pw="$(config_get_value "$s" default_admin_password)"
  # If absent => placeholder behaviour kicks in => bad.
  if [ -z "$pw" ]; then return 0; fi
  is_placeholder "$pw" && return 0
  return 1
}

is_bad_env() {
  local s="$1"
  is_sftpgo_env "$s" || return 1

  local create pw
  create="$(env_get_value "$s" SFTPGO_DATA_PROVIDER__CREATE_DEFAULT_ADMIN)"
  if [ -z "$create" ] || ! env_truthy "$create"; then
    return 1
  fi
  pw="$(env_get_value "$s" SFTPGO_DATA_PROVIDER__DEFAULT_ADMIN_PASSWORD)"
  if [ -z "$pw" ]; then return 0; fi
  is_placeholder "$pw" && return 0
  return 1
}

is_bad() {
  local f="$1"
  local stripped
  stripped="$(strip_comments "$f")"
  is_bad_config "$stripped" && return 0
  is_bad_env    "$stripped" && return 0
  return 1
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
