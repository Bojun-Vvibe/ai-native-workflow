#!/usr/bin/env bash
# detect.sh — flag kubelet configurations that LLMs commonly emit with
# anonymous authentication enabled. The kubelet exposes a read-write
# HTTPS API on port 10250 (and historically a read-only HTTP API on
# 10255). When `authentication.anonymous.enabled` is `true` (or the CLI
# flag `--anonymous-auth=true` is passed, or the legacy `--read-only-port`
# is set to a non-zero value), an unauthenticated request to the kubelet
# can list pods, exec into containers, and pull container logs — a
# documented lateral-movement primitive in every kubelet hardening guide
# (CIS Kubernetes Benchmark §4.2.1, NSA/CISA Kubernetes Hardening Guide).
#
# When asked "give me a kubelet config" or "set up a kubeadm cluster",
# LLMs routinely either:
#   * Emit a `KubeletConfiguration` YAML with `anonymous: enabled: true`.
#   * Pass `--anonymous-auth=true` on the kubelet command line.
#   * Set `readOnlyPort: 10255` (or pass `--read-only-port=10255`),
#     which exposes an unauthenticated metrics + pod-listing surface.
#   * Omit the entire `authentication:` block — the kubelet binary's
#     in-tree default for `anonymous.enabled` is `true` for plain-binary
#     deployments (the kubeadm default flips it to `false`, but only
#     when the YAML explicitly says so), so a YAML with no
#     `authentication:` block is unsafe to ship as-is.
#
# Bad patterns we flag:
#   1. KubeletConfiguration YAML with `anonymous:` block whose
#      `enabled:` is `true`.
#   2. KubeletConfiguration YAML with `readOnlyPort:` set to a non-zero
#      value.
#   3. Kubelet invocation (Dockerfile / systemd unit / shell) with
#      `--anonymous-auth=true` OR `--read-only-port=<non-zero>` OR with
#      no `--config` / `--anonymous-auth=false` / `--read-only-port=0`
#      AND no `--kubeconfig` referencing an external policy file.
#
# Exit 0 iff every bad sample is flagged AND zero good samples are flagged.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

strip_comments() {
  # YAML / systemd / shell all use `#` comments. Strip both leading-`#`
  # lines and inline `# ...` tails.
  sed -E -e 's/[[:space:]]+#.*$//' -e 's/^[[:space:]]*#.*$//' "$1"
}

is_kubelet_yaml() {
  local s="$1"
  printf '%s\n' "$s" | grep -Eiq '^[[:space:]]*kind:[[:space:]]*KubeletConfiguration\b' \
    || printf '%s\n' "$s" | grep -Eiq '^[[:space:]]*apiVersion:[[:space:]]*kubelet\.config\.k8s\.io/'
}

is_kubelet_invocation() {
  local s="$1"
  printf '%s\n' "$s" | grep -Eiq '(^|[[:space:]/"=])kubelet\b'
}

# Walk the YAML and find the `enabled:` value that sits inside an
# `anonymous:` block under `authentication:`. We do not need a full YAML
# parser — kubelet configs are flat enough that an indentation-aware
# awk pass is sufficient and keeps the detector dependency-free.
yaml_anonymous_enabled_true() {
  awk '
    function indent(s,   i) { i = match(s, /[^ ]/); return (i == 0 ? 0 : i - 1) }
    BEGIN { in_auth=0; auth_indent=-1; in_anon=0; anon_indent=-1 }
    {
      line=$0
      # Skip blank lines without resetting state — YAML blocks span them.
      if (line ~ /^[[:space:]]*$/) next
      ind = indent(line)
      stripped = line
      sub(/^[[:space:]]+/, "", stripped)

      if (in_anon && ind <= anon_indent) { in_anon=0; anon_indent=-1 }
      if (in_auth && ind <= auth_indent) { in_auth=0; auth_indent=-1 }

      if (!in_auth && stripped ~ /^authentication:[[:space:]]*$/) {
        in_auth=1; auth_indent=ind; next
      }
      if (in_auth && !in_anon && ind > auth_indent && stripped ~ /^anonymous:[[:space:]]*$/) {
        in_anon=1; anon_indent=ind; next
      }
      if (in_anon && ind > anon_indent && stripped ~ /^enabled:[[:space:]]*[Tt]rue[[:space:]]*$/) {
        print "HIT"; exit 0
      }
    }
  ' <<<"$1" | grep -q HIT
}

yaml_read_only_port_nonzero() {
  # `readOnlyPort: 10255` (or any non-zero integer) at any indentation.
  printf '%s\n' "$1" \
    | grep -Eiq '^[[:space:]]*readOnlyPort:[[:space:]]*[1-9][0-9]*[[:space:]]*$'
}

invocation_has_anonymous_auth_true() {
  local normalized
  normalized="$(printf '%s\n' "$1" | tr -d '",[]')"
  printf '%s\n' "$normalized" \
    | grep -Eiq '(^|[^[:alnum:]_-])--anonymous-auth(=|[[:space:]]+)true([^[:alnum:]_-]|$)'
}

invocation_has_read_only_port_nonzero() {
  local normalized
  normalized="$(printf '%s\n' "$1" | tr -d '",[]')"
  printf '%s\n' "$normalized" \
    | grep -Eiq '(^|[^[:alnum:]_-])--read-only-port(=|[[:space:]]+)[1-9][0-9]*([^[:alnum:]_-]|$)'
}

invocation_has_anonymous_auth_false() {
  local normalized
  normalized="$(printf '%s\n' "$1" | tr -d '",[]')"
  printf '%s\n' "$normalized" \
    | grep -Eiq '(^|[^[:alnum:]_-])--anonymous-auth(=|[[:space:]]+)false([^[:alnum:]_-]|$)'
}

invocation_references_config() {
  local normalized
  normalized="$(printf '%s\n' "$1" | tr -d '",[]')"
  printf '%s\n' "$normalized" \
    | grep -Eiq '(^|[^[:alnum:]_-])--config(=|[[:space:]]+)[^[:space:]]+'
}

is_bad() {
  local f="$1"
  local stripped
  stripped="$(strip_comments "$f")"

  # Rule 3 — pure invocation (no embedded KubeletConfiguration).
  if is_kubelet_invocation "$stripped" && ! is_kubelet_yaml "$stripped"; then
    if invocation_has_anonymous_auth_true "$stripped"; then return 0; fi
    if invocation_has_read_only_port_nonzero "$stripped"; then return 0; fi
    if ! invocation_has_anonymous_auth_false "$stripped" \
       && ! invocation_references_config "$stripped"; then
      return 0
    fi
    return 1
  fi

  # Rules 1 & 2 — KubeletConfiguration YAML.
  if is_kubelet_yaml "$stripped"; then
    if yaml_anonymous_enabled_true "$stripped"; then return 0; fi
    if yaml_read_only_port_nonzero "$stripped"; then return 0; fi
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
