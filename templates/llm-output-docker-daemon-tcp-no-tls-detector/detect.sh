#!/usr/bin/env bash
# detect.sh — flag Docker daemon launch / config snippets that expose the
# Docker API over TCP without TLS. The Docker daemon API has no
# authentication: anyone reaching `tcp://host:2375` can `docker run -v
# /:/host` and walk out as root on the host. Upstream docs are explicit
# that 2375 is plaintext and TLS (and a CA-pinned client cert) is the
# only supported auth boundary.
#
# Bad patterns:
#   1. `dockerd ... -H tcp://...` (or `--host=tcp://...`) without
#      `--tls`, `--tlsverify`, or `--tlscacert` on the same line.
#   2. systemd unit `ExecStart=` with the same shape.
#   3. `/etc/docker/daemon.json` with `"hosts": [..., "tcp://..."]` and
#      no `"tlsverify": true` (or no `"tls": true`) and no `"tlscacert"`.
#   4. Any line binding to port 2375 specifically (the well-known
#      plaintext port) — even `-H 0.0.0.0:2375` shorthand.
#   5. Compose / k8s `command:` array form for dockerd with -H tcp://
#      and no TLS flags.
#
# Exit 0 iff every samples/bad/* is flagged AND every samples/good/* is clean.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

is_bad() {
  local f="$1"
  local uncommented
  uncommented=$(grep -Ev '^[[:space:]]*#' "$f" || true)

  # Gate: file must reference dockerd / docker daemon / daemon.json to
  # avoid false positives on unrelated TCP configs.
  if ! { echo "$f" | grep -qiE 'docker|daemon\.json'; } \
     && ! grep -qiE 'dockerd|daemon\.json|docker[[:space:]_-]daemon' "$f"; then
    return 1
  fi

  # JSON form (daemon.json): look for a "hosts" array containing tcp://
  # and the absence of tlsverify/tls/tlscacert.
  if echo "$uncommented" | grep -Eq '"hosts"[[:space:]]*:[[:space:]]*\[[^]]*"tcp://'; then
    if ! echo "$uncommented" | grep -Eq '"(tlsverify|tls)"[[:space:]]*:[[:space:]]*true' \
       && ! echo "$uncommented" | grep -Eq '"tlscacert"[[:space:]]*:'; then
      return 0
    fi
  fi

  # Rule 4: explicit :2375 binding anywhere uncommented, with no TLS flags.
  if echo "$uncommented" | grep -Eq -- '(tcp://[^"[:space:]]*:2375|0\.0\.0\.0:2375|:2375["[:space:]])'; then
    if ! echo "$uncommented" | grep -Eq -- '(--tlsverify|--tlscacert|--tls(\b|=))' \
       && ! echo "$uncommented" | grep -Eq '"(tlsverify|tls)"[[:space:]]*:[[:space:]]*true'; then
      return 0
    fi
  fi

  # Rule 1/2/5: dockerd / ExecStart with -H tcp:// (or --host=tcp://) and no TLS.
  # Walk line-by-line so a TLS flag on a *different* dockerd line doesn't
  # whitewash a plaintext binding.
  while IFS= read -r line; do
    case "$line" in
      *dockerd*|*ExecStart=*|*\"dockerd\"*) ;;
      *) continue ;;
    esac
    if echo "$line" | grep -Eq -- '(-H|--host)["'"'"']?[[:space:],=]+["'"'"']?tcp://'; then
      if ! echo "$line" | grep -Eq -- '(--tlsverify|--tlscacert|--tls(\b|=))'; then
        return 0
      fi
    fi
  done <<EOF
$uncommented
EOF

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
