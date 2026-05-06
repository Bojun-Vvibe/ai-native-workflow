#!/usr/bin/env bash
# llm-output-netdata-web-bind-public-no-auth-detector
#
# Flags Netdata deployments whose `netdata.conf` exposes the embedded
# web server on a public-facing socket without any authentication —
# i.e. the [web] section binds to `*`, `0.0.0.0`, `::`, or a non-loopback
# interface AND `allow connections from` is wide open (`*` or absent
# default) AND no bearer-token / API-key gate is configured.
#
# Reads INI-style `netdata.conf` files (and obvious aliases) given a
# path to a file or a directory (recursive).
#
# Exit codes:
#   0   PASS  no public-bind-without-auth observed
#   1   FAIL  at least one public-bind-without-auth observed
#   2   usage error
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <netdata.conf-or-dir>" >&2
  exit 2
fi

target="$1"
if [ ! -e "$target" ]; then
  echo "no such path: $target" >&2
  exit 2
fi

found=0

# Strip leading/trailing whitespace.
trim() {
  s="$1"
  # leading
  while :; do
    case "$s" in
      ' '*|'	'*) s="${s#?}" ;;
      *) break ;;
    esac
  done
  # trailing
  while :; do
    case "$s" in
      *' '|*'	') s="${s%?}" ;;
      *) break ;;
    esac
  done
  printf '%s' "$s"
}

is_public_bind() {
  v="$1"
  case "$v" in
    '*'|'0.0.0.0'|'::'|'[::]'|'::0'|'0:0:0:0:0:0:0:0') return 0 ;;
  esac
  # `bind socket to IP` accepts a space-separated list. Any single
  # public token in the list is enough.
  for tok in $v; do
    case "$tok" in
      '*'|'0.0.0.0'|'::'|'[::]'|'::0') return 0 ;;
      127.*|::1|localhost) continue ;;
      # explicit non-loopback IPv4/IPv6 literal: treat as public
      # unless it is in RFC1918; we still treat private-LAN bind
      # as public exposure for the purposes of this detector
      # because there is still no auth gate.
      *.*.*.*|*:*) return 0 ;;
    esac
  done
  return 1
}

is_open_acl() {
  v="$1"
  case "$v" in
    ''|'*'|'all'|'0.0.0.0/0'|'::/0') return 0 ;;
  esac
  # any list containing '*' counts as open
  for tok in $v; do
    [ "$tok" = '*' ] && return 0
  done
  return 1
}

scan_one() {
  f="$1"
  in_web=0
  bind_val=""
  acl_val="__UNSET__"
  bearer_set=0
  mode_val=""
  while IFS= read -r raw || [ -n "$raw" ]; do
    line="$(trim "$raw")"
    case "$line" in
      \#*|';'*|'') continue ;;
    esac
    case "$line" in
      '['*']')
        # closing previous section: evaluate if it was [web]
        if [ "$in_web" -eq 1 ]; then
          evaluate "$f"
        fi
        # open new section
        sect="${line#[}"; sect="${sect%]}"
        sect_lc="$(printf '%s' "$sect" | tr 'A-Z' 'a-z')"
        if [ "$sect_lc" = "web" ]; then
          in_web=1
          bind_val=""
          acl_val="__UNSET__"
          bearer_set=0
          mode_val=""
        else
          in_web=0
        fi
        continue
        ;;
    esac
    [ "$in_web" -eq 1 ] || continue
    # key = value
    key="${line%%=*}"
    val="${line#*=}"
    [ "$key" = "$line" ] && continue
    key="$(trim "$key")"
    val="$(trim "$val")"
    key_lc="$(printf '%s' "$key" | tr 'A-Z' 'a-z')"
    case "$key_lc" in
      'bind socket to ip'|'bind to') bind_val="$val" ;;
      'allow connections from')      acl_val="$val" ;;
      'bearer token protection'|'bearer token')
        case "$(printf '%s' "$val" | tr 'A-Z' 'a-z')" in
          yes|on|true|1) bearer_set=1 ;;
        esac
        ;;
      'mode') mode_val="$(printf '%s' "$val" | tr 'A-Z' 'a-z')" ;;
    esac
  done < "$f"
  if [ "$in_web" -eq 1 ]; then
    evaluate "$f"
  fi
}

evaluate() {
  f="$1"
  # If the web server is disabled outright, no exposure.
  case "$mode_val" in
    none|static-threaded) ;;  # static-threaded still serves; treat as on
  esac
  if [ "$mode_val" = "none" ]; then
    return
  fi
  # Default bind on netdata is `*` if unset.
  effective_bind="$bind_val"
  [ -z "$effective_bind" ] && effective_bind='*'
  # Default ACL is `*` (open) if unset.
  effective_acl="$acl_val"
  if [ "$effective_acl" = "__UNSET__" ]; then
    effective_acl='*'
  fi
  if is_public_bind "$effective_bind" && is_open_acl "$effective_acl" \
     && [ "$bearer_set" -eq 0 ]; then
    echo "FAIL: $f: [web] public bind '$effective_bind' with allow-from '$effective_acl' and no bearer-token gate"
    found=1
  fi
}

if [ -d "$target" ]; then
  while IFS= read -r f; do
    case "$(basename "$f")" in
      netdata.conf|netdata.conf.*|*.netdata.conf)
        [ -f "$f" ] && scan_one "$f"
        ;;
    esac
  done <<EOF
$(find "$target" -type f 2>/dev/null)
EOF
else
  scan_one "$target"
fi

if [ "$found" -eq 0 ]; then
  echo "PASS: $target"
  exit 0
fi
exit 1
