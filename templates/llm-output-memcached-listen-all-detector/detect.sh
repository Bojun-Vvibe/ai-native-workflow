#!/usr/bin/env bash
# detect.sh — flag memcached config / launch snippets that expose the
# binary text/UDP protocol to every interface without SASL or a localhost
# bind. Memcached has no built-in auth in its default build (SASL must be
# enabled at compile + runtime), so a 0.0.0.0 bind on :11211 is a direct
# unauthenticated cache read/write — and historically a UDP amplification
# vector (CVE-2018-1000115 era).
#
# Bad patterns:
#   1. CLI / systemd / Dockerfile / compose `-l 0.0.0.0` or `--listen=0.0.0.0`
#      (or missing -l entirely on a public-bound container) without `-S`
#      (SASL) anywhere in the same launch line.
#   2. `/etc/memcached.conf` style: an uncommented `-l 0.0.0.0` line and
#      no uncommented `-S` line.
#   3. UDP enabled (`-U 11211` or non-zero `-U`) without a bind to loopback
#      — UDP memcached is the amplification primitive; modern packages ship
#      `-U 0` for a reason.
#   4. Compose / k8s `command:` array containing memcached invocation with
#      `-l 0.0.0.0` and no `-S`.
#
# Exit 0 iff every samples/bad/* is flagged AND every samples/good/* is clean.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

is_bad() {
  local f="$1"
  # Strip comment-only lines for the "uncommented" checks. We use a temp
  # filtered view via grep -v.
  local uncommented
  uncommented=$(grep -Ev '^[[:space:]]*#' "$f" || true)

  # Heuristic: only consider files that look memcached-related to reduce
  # false positives in mixed-content samples. We accept if the file name
  # or content references memcached/memcache.
  if ! { echo "$f" | grep -qiE 'memcache'; } \
     && ! grep -qiE 'memcache' "$f"; then
    return 1
  fi

  # Rule 1/4: CLI / compose with -l 0.0.0.0 (or --listen=0.0.0.0) and no -S.
  # Tolerate JSON-array form: "-l", "0.0.0.0" — i.e. quote/comma/space between.
  if echo "$uncommented" | grep -Eq -- '(^|[[:space:]"'"'"'])(-l|--listen)["'"'"']?[[:space:],=]+["'"'"']?0\.0\.0\.0' \
     && ! echo "$uncommented" | grep -Eq -- '(^|[[:space:]"'"'"'])-S(["'"'"',[:space:]]|$)'; then
    return 0
  fi

  # Rule 2: conf-file form: uncommented `-l 0.0.0.0` line and no uncommented `-S`
  if echo "$uncommented" | grep -Eq '^[[:space:]]*-l[[:space:]]+0\.0\.0\.0' \
     && ! echo "$uncommented" | grep -Eq '^[[:space:]]*-S([[:space:]]|$)'; then
    return 0
  fi

  # Rule 3: UDP enabled with non-zero port and no loopback bind.
  # Tolerate JSON-array form for both -U and the loopback check.
  if echo "$uncommented" | grep -Eq -- '(^|[[:space:]"'"'"'])(-U|--udp-port)["'"'"']?[[:space:],=]+["'"'"']?([1-9][0-9]*)'; then
    # If there's an explicit loopback bind, it's tolerable.
    if ! echo "$uncommented" | grep -Eq -- '(-l|--listen)["'"'"']?[[:space:],=]+["'"'"']?(127\.|::1|localhost)'; then
      return 0
    fi
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
