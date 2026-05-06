#!/usr/bin/env bash
# detect.sh — flag Headscale configurations and ACL policies that
# LLMs routinely emit with no effective access control. Headscale is
# the open-source control plane for Tailscale; without an ACL policy
# wired in, every node on the tailnet can reach every other node on
# every port. Joining one rogue device exposes every internal admin
# panel, SSH, kubelet, and DB bound to the tailnet interface.
#
# Bad patterns (any one is sufficient):
#   1. Headscale-shaped config.yaml with no policy.path /
#      acl_policy_path / policy.mode set to a meaningful value.
#   2. Headscale config.yaml whose policy.path or acl_policy_path
#      is the empty string.
#   3. ACL policy file (HuJSON-ish / YAML with `acls:`) whose only
#      rule is action=accept, src=["*"], dst=["*:*"] (or `"*"`).
#   4. CLI: `headscale serve --policy ""` or
#      `headscale ... --policy-mode file --policy-path ""`.
#
# Good patterns are the inverse: a real path with at least one
# non-wildcard src/dst, or `policy.mode: database`.
#
# Exit 0 iff every bad sample is flagged AND zero good samples are flagged.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

strip_yaml_comments() {
  # YAML / HuJSON: `#` and `//` start line comments.
  sed -E -e 's@[[:space:]]+//.*$@@' -e 's@^[[:space:]]*//.*$@@' \
         -e 's/[[:space:]]+#.*$//' -e 's/^[[:space:]]*#.*$//' "$1"
}

is_headscale_config() {
  # Strong markers for a Headscale config.yaml.
  local s="$1"
  printf '%s\n' "$s" | grep -Eq '^[[:space:]]*server_url[[:space:]]*:' \
    || return 1
  printf '%s\n' "$s" | grep -Eq '^[[:space:]]*(listen_addr|private_key_path|noise|db_type|database|metrics_listen_addr|grpc_listen_addr|derp)[[:space:]]*:' \
    || return 1
  return 0
}

is_headscale_cli() {
  local s="$1"
  printf '%s\n' "$s" | grep -Eq '(^|[[:space:]/"=])headscale[[:space:]]+(serve|server|--config|nodes|policy)\b'
}

is_acl_policy_file() {
  # YAML/HuJSON ACL with `acls:` list.
  local s="$1"
  printf '%s\n' "$s" | grep -Eq '^[[:space:]]*"?acls"?[[:space:]]*:' \
    || return 1
  # Reject things that are clearly the headscale config (which has
  # `acl_policy_path:` not `acls:`).
  if printf '%s\n' "$s" | grep -Eq '^[[:space:]]*server_url[[:space:]]*:'; then
    return 1
  fi
  return 0
}

policy_path_value() {
  # Print the value of policy.path / acl_policy_path / policy_path.
  # Empty if not present. Quotes stripped.
  local s="$1"
  # Top-level acl_policy_path:
  local v
  v="$(printf '%s\n' "$s" | grep -E '^[[:space:]]*acl_policy_path[[:space:]]*:' \
        | head -n1 | sed -E 's/^[[:space:]]*acl_policy_path[[:space:]]*:[[:space:]]*//')"
  if [ -n "$v" ]; then
    printf '%s' "$v" | sed -E 's/^["'\''](.*)["'\'']$/\1/' | sed -E 's/[[:space:]]+$//'
    return 0
  fi
  # Nested policy: { path: ... } block. We approximate by finding
  # a `path:` line that is indented under a `policy:` parent.
  # Simple two-pass: scan for `policy:` then the next `path:` before
  # any non-indented key.
  awk '
    BEGIN { in_policy=0 }
    /^[^[:space:]].*:/ { if (in_policy && $0 !~ /^policy[[:space:]]*:/) in_policy=0 }
    /^policy[[:space:]]*:/ { in_policy=1; next }
    in_policy && /^[[:space:]]+path[[:space:]]*:/ {
      sub(/^[[:space:]]+path[[:space:]]*:[[:space:]]*/,"")
      print
      exit
    }
  ' <<<"$s" | sed -E 's/^["'\''](.*)["'\'']$/\1/' | sed -E 's/[[:space:]]+$//'
}

policy_mode_value() {
  local s="$1"
  awk '
    BEGIN { in_policy=0 }
    /^[^[:space:]].*:/ { if (in_policy && $0 !~ /^policy[[:space:]]*:/) in_policy=0 }
    /^policy[[:space:]]*:/ { in_policy=1; next }
    in_policy && /^[[:space:]]+mode[[:space:]]*:/ {
      sub(/^[[:space:]]+mode[[:space:]]*:[[:space:]]*/,"")
      print
      exit
    }
  ' <<<"$s" | sed -E 's/^["'\''](.*)["'\'']$/\1/' | sed -E 's/[[:space:]]+$//'
}

acl_is_permit_all() {
  # The whole acls: list contains a single accept rule with src/dst
  # wildcards. We're permissive about whitespace and ordering.
  local s="$1"
  # Look for action: accept with src ["*"] and dst ["*:*"] or "*".
  # We allow either YAML list or HuJSON array.
  printf '%s\n' "$s" | grep -Eq '"?action"?[[:space:]]*:[[:space:]]*"?accept"?' || return 1
  # src wildcard
  printf '%s\n' "$s" \
    | grep -Eq '"?src"?[[:space:]]*:[[:space:]]*\[[[:space:]]*"\*"[[:space:]]*\]' \
    || return 1
  # dst wildcard (`*:*` or `*`)
  printf '%s\n' "$s" \
    | grep -Eq '"?(dst|dest|destination)"?[[:space:]]*:[[:space:]]*\[[[:space:]]*"(\*|\*:\*)"[[:space:]]*\]' \
    || return 1
  # And there is no non-wildcard rule. We approximate by checking
  # there is no other action: accept line whose src is not `["*"]`.
  # Cheap check: number of `"*"` tokens >= number of non-wildcard
  # CIDR/tag tokens in src/dst lines.
  if printf '%s\n' "$s" | grep -Eq '"(tag:|group:|autogroup:|[0-9]{1,3}(\.[0-9]{1,3}){3})'; then
    return 1
  fi
  return 0
}

is_bad_config() {
  local s="$1"
  is_headscale_config "$s" || return 1

  local mode
  mode="$(policy_mode_value "$s" | tr 'A-Z' 'a-z')"
  if [ "$mode" = "database" ]; then
    return 1
  fi

  local path
  path="$(policy_path_value "$s")"
  if [ -z "$path" ]; then
    return 0
  fi
  return 1
}

is_bad_cli() {
  local s="$1"
  is_headscale_cli "$s" || return 1
  # --policy "" / --policy '' / --policy-path ""
  if printf '%s\n' "$s" \
      | grep -Eq -- '--(policy|policy-path)[[:space:]]+("|'\'')("|'\'')(\b|[[:space:]]|$)'; then
    return 0
  fi
  if printf '%s\n' "$s" \
      | grep -Eq -- '--(policy|policy-path)=("|'\'')("|'\'')(\b|[[:space:]]|$)'; then
    return 0
  fi
  return 1
}

is_bad_acl() {
  local s="$1"
  is_acl_policy_file "$s" || return 1
  acl_is_permit_all "$s"
}

is_bad() {
  local f="$1"
  local stripped
  stripped="$(strip_yaml_comments "$f")"
  is_bad_config "$stripped" && return 0
  is_bad_cli    "$stripped" && return 0
  is_bad_acl    "$stripped" && return 0
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
