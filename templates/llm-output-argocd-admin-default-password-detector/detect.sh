#!/usr/bin/env bash
# detect.sh — flag Argo CD install / config snippets that leave the bootstrap
# admin account exposed:
#   1. argocd-secret with `admin.password:` set to a known weak/default value
#      (literal "admin", "password", "argocd", or a base64 encoding of those)
#   2. argocd login transcripts that pass `--password admin` (or similar
#      defaults) on the command line
#   3. argocd-cm with `admin.enabled: "true"` AND no companion change to
#      `admin.passwordMtime` (i.e. the bootstrap password was never rotated)
#   4. Helm / kustomize values that hardcode `configs.secret.argocdServerAdminPassword`
#      to a known weak literal
#
# Exit 0 iff no bad files match.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

# base64 of: admin, password, argocd, admin123
WEAK_B64='YWRtaW4=|cGFzc3dvcmQ=|YXJnb2Nk|YWRtaW4xMjM='

is_bad() {
  local f="$1"
  # Rule 1a: literal weak value in admin.password
  if grep -Eiq '^[[:space:]]*admin\.password[[:space:]]*:[[:space:]]*"?(admin|password|argocd|admin123|changeme)"?[[:space:]]*$' "$f"; then
    return 0
  fi
  # Rule 1b: base64 encoded weak value in admin.password (Secret data:)
  if grep -Eq "^[[:space:]]*admin\.password[[:space:]]*:[[:space:]]*(${WEAK_B64})[[:space:]]*$" "$f"; then
    return 0
  fi
  # Rule 2: argocd login --password <weak>
  if grep -Eiq 'argocd[[:space:]]+login\b.*--password[[:space:]]+(admin|password|argocd|admin123|changeme)([[:space:]]|$)' "$f"; then
    return 0
  fi
  # Rule 3: admin.enabled true AND no passwordMtime rotation marker anywhere in file
  if grep -Eiq '^[[:space:]]*admin\.enabled[[:space:]]*:[[:space:]]*"?true"?[[:space:]]*$' "$f" \
     && ! grep -Eq 'admin\.passwordMtime' "$f" \
     && ! grep -Eq 'admin\.passwordHash' "$f"; then
    return 0
  fi
  # Rule 4: helm/kustomize hardcoded weak admin password
  if grep -Eiq '(argocdServerAdminPassword|argocd_server_admin_password)[[:space:]]*[:=][[:space:]]*"?(admin|password|argocd|admin123|changeme)"?[[:space:]]*$' "$f"; then
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
