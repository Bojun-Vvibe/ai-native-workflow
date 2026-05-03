#!/usr/bin/env bash
# detector.sh — flag Kibana configs that disable Elasticsearch TLS verification.
#
# Rules:
#  R1: kibana.yml-style key `elasticsearch.ssl.verificationMode: none`
#  R2: nested yaml under `elasticsearch:` -> `ssl:` -> `verificationMode: none`
#  R3: env var ELASTICSEARCH_SSL_VERIFICATIONMODE set to none (any case)
#  R4: yaml mapping form ELASTICSEARCH_SSL_VERIFICATIONMODE: "none"
#
# Exit 0 iff every bad sample matches and zero good samples match.
set -u

is_bad() {
  local f="$1"

  # R1: dotted key form
  if grep -Eq '(^|[[:space:]])elasticsearch\.ssl\.verificationMode[[:space:]]*:[[:space:]]*"?[Nn][Oo][Nn][Ee]"?([[:space:]]|$)' "$f"; then
    return 0
  fi

  # R2: nested yaml — look for verificationMode: none under an elasticsearch.ssl block.
  # Use awk to track context.
  if awk '
    /^[[:space:]]*elasticsearch[[:space:]]*:/ { in_es=1; es_indent=match($0,/[^ ]/)-1; next }
    in_es && /^[[:space:]]*ssl[[:space:]]*:/ {
      ind=match($0,/[^ ]/)-1
      if (ind > es_indent) { in_ssl=1; ssl_indent=ind; next }
    }
    in_ssl && /^[[:space:]]*verificationMode[[:space:]]*:[[:space:]]*"?[Nn][Oo][Nn][Ee]"?[[:space:]]*$/ {
      ind=match($0,/[^ ]/)-1
      if (ind > ssl_indent) { hit=1 }
    }
    # Reset blocks when indentation drops
    in_ssl && /^[^[:space:]]/ { in_ssl=0; in_es=0 }
    in_es && /^[^[:space:]]/ { in_es=0 }
    END { exit (hit ? 0 : 1) }
  ' "$f" >/dev/null; then
    return 0
  fi

  # R3: env var (shell export, dotenv, Dockerfile ENV, systemd Environment=)
  if grep -Eiq '(^|[[:space:]"])(export[[:space:]]+|ENV[[:space:]]+)?ELASTICSEARCH_SSL_VERIFICATIONMODE[[:space:]]*=[[:space:]]*"?none"?([[:space:]]|$)' "$f"; then
    return 0
  fi
  if grep -Eiq '^[[:space:]]*Environment=[[:space:]]*"?ELASTICSEARCH_SSL_VERIFICATIONMODE=none"?' "$f"; then
    return 0
  fi

  # R4: yaml mapping form (compose environment block, k8s env list)
  if grep -Eiq '(^|[[:space:]-])ELASTICSEARCH_SSL_VERIFICATIONMODE[[:space:]]*:[[:space:]]*"?none"?[[:space:]]*$' "$f"; then
    return 0
  fi
  # k8s env list: name: ELASTICSEARCH_SSL_VERIFICATIONMODE then value: none
  if awk '
    tolower($0) ~ /name:[[:space:]]*"?elasticsearch_ssl_verificationmode"?/ { found=NR }
    found && NR<=found+3 && tolower($0) ~ /value:[[:space:]]*"?none"?[[:space:]]*$/ { hit=1 }
    END { exit (hit ? 0 : 1) }
  ' "$f" >/dev/null; then
    return 0
  fi

  return 1
}

bad_hits=0; bad_total=0; good_hits=0; good_total=0
for f in "$@"; do
  case "$f" in
    *examples/bad/*)  bad_total=$((bad_total+1)) ;;
    *examples/good/*) good_total=$((good_total+1)) ;;
  esac
  if is_bad "$f"; then
    echo "BAD  $f"
    case "$f" in
      *examples/bad/*)  bad_hits=$((bad_hits+1)) ;;
      *examples/good/*) good_hits=$((good_hits+1)) ;;
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
