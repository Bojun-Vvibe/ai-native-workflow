#!/usr/bin/env bash
# detector.sh — flag Vault configs that disable mlock in production-shaped deployments.
#
# Rules:
#  R1: HCL top-level `disable_mlock = true` (with various quoting/spacing)
#  R2: Env var VAULT_DISABLE_MLOCK set truthy (1, true, "true", yes)
#  R3: Inline HCL in compose/k8s manifest containing disable_mlock = true
#  R4: Helm values yaml with disable_mlock: true under server.* (or extraArgs containing it)
#
# Exit 0 iff every bad sample matches and zero good samples match.
set -u

is_bad() {
  local f="$1"

  # R1 / R3: HCL form. Match disable_mlock = true OR "disable_mlock" = true
  if grep -Eq '(^|[[:space:]"])disable_mlock[[:space:]"]*=[[:space:]]*"?true"?([[:space:]]|$)' "$f"; then
    return 0
  fi

  # R4: yaml form. disable_mlock: true (Helm values, k8s ConfigMap)
  if grep -Eq '(^|[[:space:]-])disable_mlock[[:space:]]*:[[:space:]]*"?(true|yes)"?([[:space:]]|$)' "$f"; then
    return 0
  fi

  # R2: env var form. VAULT_DISABLE_MLOCK=1|true|"true"|yes (shell, dotenv, Dockerfile ENV)
  if grep -Eq '(^|[[:space:]"])(export[[:space:]]+|ENV[[:space:]]+)?VAULT_DISABLE_MLOCK[[:space:]]*=[[:space:]]*"?(1|true|yes|TRUE|YES|True)"?([[:space:]]|$)' "$f"; then
    return 0
  fi
  # R2b: yaml mapping form. VAULT_DISABLE_MLOCK: "1" / true (compose environment block)
  if grep -Eq '(^|[[:space:]-])VAULT_DISABLE_MLOCK[[:space:]]*:[[:space:]]*"?(1|true|yes|TRUE|YES|True)"?[[:space:]]*$' "$f"; then
    return 0
  fi
  # systemd Environment= form
  if grep -Eq '^[[:space:]]*Environment=[[:space:]]*"?VAULT_DISABLE_MLOCK=(1|true|yes|TRUE|YES|True)"?' "$f"; then
    return 0
  fi
  # k8s env list form: name: VAULT_DISABLE_MLOCK ... value: "true"
  if awk '
    /name:[[:space:]]*"?VAULT_DISABLE_MLOCK"?/ { found=NR }
    found && NR<=found+3 && /value:[[:space:]]*"?(1|true|yes|TRUE|YES|True)"?[[:space:]]*$/ { hit=1 }
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
