#!/usr/bin/env bash
# detect.sh — flag MariaDB / MySQL configuration and start-up snippets that
# disable the privilege system entirely or render it inert. The classic
# offenders LLMs emit when asked "I forgot the root password, what do I do":
#
#   1. `skip-grant-tables` (or `skip_grant_tables`) in my.cnf / my.ini /
#      conf.d/*.cnf — every connection becomes effectively root, no auth.
#   2. `mysqld --skip-grant-tables` baked into a Dockerfile/CMD/entrypoint
#      or a docker-compose `command:` line, even when the flag is paired
#      with `--skip-networking=0` (the dangerous "let me reset it remotely"
#      pattern).
#   3. `MYSQL_ALLOW_EMPTY_PASSWORD=yes` (or `=true`/`=1`) in env files,
#      compose files, or Dockerfile `ENV` lines — official mysql/mariadb
#      images explicitly document this as "do not use in production".
#   4. SQL bootstrap scripts that issue `GRANT ALL PRIVILEGES ON *.* TO
#      'root'@'%' IDENTIFIED BY ''` (empty password) or
#      `... IDENTIFIED BY 'root'` / `'password'` / `'admin'`.
#
# Exit 0 iff every bad sample is flagged AND zero good samples are flagged.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

# Strip shell-style `#` comments and SQL `--` line comments before matching.
# (We deliberately keep `[mysqld]` section headers intact — they start with
# `[`, not `#`.)
strip_comments() {
  sed -E -e 's/[[:space:]]+#.*$//' -e 's/^[[:space:]]*#.*$//' \
         -e 's/--[[:space:]].*$//' "$1"
}

is_bad() {
  local f="$1"
  local stripped
  stripped="$(strip_comments "$f")"

  # Rule 1: skip-grant-tables / skip_grant_tables as a my.cnf directive
  # (bare line, optionally `=` or `=1`/`=true`/`=ON`).
  if printf '%s\n' "$stripped" \
     | grep -Eiq '^[[:space:]]*skip[-_]grant[-_]tables([[:space:]]*=[[:space:]]*(1|true|on|yes))?[[:space:]]*$'; then
    return 0
  fi

  # Rule 2: mysqld / mariadbd command line carrying --skip-grant-tables
  # (covers Dockerfile CMD/RUN, compose `command:`, entrypoint scripts).
  if printf '%s\n' "$stripped" | grep -Eiq '(mysqld|mariadbd)[^#]*--skip[-_]grant[-_]tables\b'; then
    return 0
  fi

  # Rule 3: MYSQL_ALLOW_EMPTY_PASSWORD or MARIADB_ALLOW_EMPTY_(ROOT_)PASSWORD
  # set to yes/true/1 (env file, compose env: list, Dockerfile ENV).
  if printf '%s\n' "$stripped" \
     | grep -Eiq '(MYSQL|MARIADB)_ALLOW_EMPTY(_ROOT)?_PASSWORD[[:space:]]*[:=][[:space:]]*"?(yes|true|1)"?[[:space:]]*$'; then
    return 0
  fi

  # Rule 4: GRANT ALL ... TO 'root'@'<anything>' IDENTIFIED BY '<weak>'.
  # Collapse newlines so multi-line GRANT statements still match.
  local oneline grant_prefix
  oneline="$(printf '%s\n' "$stripped" | tr '\n' ' ')"
  grant_prefix="GRANT[[:space:]]+ALL([[:space:]]+PRIVILEGES)?[[:space:]]+ON[[:space:]]+\\*\\.\\*[[:space:]]+TO[[:space:]]+'root'@'[^']*'[[:space:]]+IDENTIFIED[[:space:]]+BY[[:space:]]+"
  # 4a: empty password
  if printf '%s\n' "$oneline" | grep -Eiq "${grant_prefix}''"; then
    return 0
  fi
  # 4b: known-weak passwords
  if printf '%s\n' "$oneline" | grep -Eiq "${grant_prefix}'(root|password|admin|123456|mysql|mariadb)'"; then
    return 0
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
