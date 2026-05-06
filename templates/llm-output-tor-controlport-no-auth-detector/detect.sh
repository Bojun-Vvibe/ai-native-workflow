#!/usr/bin/env bash
# detect.sh — flag Tor `torrc` configurations that LLMs routinely
# emit with a TCP `ControlPort` open AND no authentication
# mechanism configured. Tor's control port speaks a text protocol
# that lets a connected client reload config, fetch keys, change
# the SocksPort, dump circuits, and (critically) issue
# `SIGNAL NEWNYM` / `GETINFO` / `SETCONF` commands. With no auth,
# any local process — and, if the port binds publicly, any host on
# the network — can fully control the relay or client.
#
# Bad patterns (any one is sufficient):
#   1. `ControlPort <num>` (TCP form) with no `HashedControlPassword`,
#      no `CookieAuthentication 1`, and no `ControlSocket` Unix-only
#      replacement in the same file.
#   2. `ControlPort <num>` together with `CookieAuthentication 0`
#      (explicit disable) and no `HashedControlPassword`.
#   3. `ControlPort 0.0.0.0:<num>` or `ControlPort *:<num>` (public
#      bind) with `CookieAuthentication 1` only — cookie auth on a
#      public port is useless because the cookie file is local.
#   4. `ControlPort <num>` with `HashedControlPassword` set to the
#      empty string or a literal placeholder like `CHANGEME`.
#
# Good patterns are the inverse: ControlPort omitted, ControlPort
# accompanied by a real HashedControlPassword (16:... hex form),
# ControlPort with CookieAuthentication 1 and a loopback bind, or
# ControlSocket replacing ControlPort entirely.
#
# Exit 0 iff every bad sample is flagged AND zero good samples are flagged.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

strip_comments() {
  # torrc uses `#` line comments only.
  sed -E -e 's/[[:space:]]+#.*$//' -e 's/^[[:space:]]*#.*$//' "$1"
}

is_torrc() {
  local s="$1"
  # torrc fingerprints: SocksPort / ControlPort / ORPort / DataDirectory
  # / HiddenServiceDir keywords. We require at least one to be in scope.
  printf '%s\n' "$s" \
    | grep -Eq '^[[:space:]]*(SocksPort|ControlPort|ORPort|DataDirectory|HiddenServiceDir|ControlSocket|CookieAuthentication|HashedControlPassword)\b'
}

has_tcp_controlport() {
  # Match `ControlPort <something>` where <something> is not the
  # literal `0` (which disables it) and not a `unix:` path.
  printf '%s\n' "$1" \
    | grep -E '^[[:space:]]*ControlPort[[:space:]]+' \
    | grep -Ev '^[[:space:]]*ControlPort[[:space:]]+0[[:space:]]*$' \
    | grep -Eqv '^[[:space:]]*ControlPort[[:space:]]+unix:'
}

controlport_value() {
  printf '%s\n' "$1" \
    | grep -E '^[[:space:]]*ControlPort[[:space:]]+' \
    | head -n1 \
    | sed -E 's/^[[:space:]]*ControlPort[[:space:]]+//' \
    | awk '{print $1}'
}

controlport_is_public() {
  local v="$1"
  case "$v" in
    "0.0.0.0:"*|"*:"*|"::"*|"[::]"*) return 0 ;;
    *) return 1 ;;
  esac
}

has_hashed_password() {
  # HashedControlPassword must be present AND non-empty AND not a
  # placeholder like CHANGEME / TODO / xxx.
  local line v
  line="$(printf '%s\n' "$1" \
    | grep -E '^[[:space:]]*HashedControlPassword[[:space:]]+' \
    | head -n1)"
  [ -n "$line" ] || return 1
  v="$(printf '%s' "$line" \
        | sed -E 's/^[[:space:]]*HashedControlPassword[[:space:]]+//' \
        | awk '{print $1}')"
  [ -n "$v" ] || return 1
  case "$(printf '%s' "$v" | tr 'A-Z' 'a-z')" in
    ""|"changeme"|"todo"|"xxx"|"placeholder"|"replaceme") return 1 ;;
  esac
  return 0
}

cookie_auth_value() {
  # Returns 1, 0, or empty.
  printf '%s\n' "$1" \
    | grep -E '^[[:space:]]*CookieAuthentication[[:space:]]+' \
    | tail -n1 \
    | sed -E 's/^[[:space:]]*CookieAuthentication[[:space:]]+//' \
    | awk '{print $1}'
}

is_bad() {
  local f="$1"
  local s
  s="$(strip_comments "$f")"
  is_torrc "$s" || return 1
  has_tcp_controlport "$s" || return 1

  local cp ck has_hpw
  cp="$(controlport_value "$s")"
  ck="$(cookie_auth_value "$s")"
  if has_hashed_password "$s"; then has_hpw=1; else has_hpw=0; fi

  # Pattern 4: HashedControlPassword present but empty/placeholder
  # is handled by has_hashed_password returning 1 already.

  # Pattern 3: public bind with cookie-only auth.
  if controlport_is_public "$cp"; then
    if [ "$has_hpw" = "0" ]; then
      # Public bind + (cookie-only OR no auth) → bad.
      return 0
    fi
  fi

  # Pattern 2: explicit CookieAuthentication 0 and no hashed pw.
  if [ "$ck" = "0" ] && [ "$has_hpw" = "0" ]; then
    return 0
  fi

  # Pattern 1: no auth at all.
  if [ "$has_hpw" = "0" ] && [ "$ck" != "1" ]; then
    return 0
  fi

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
