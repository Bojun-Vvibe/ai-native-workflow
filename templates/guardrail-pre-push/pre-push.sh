#!/usr/bin/env bash
# Generalized pre-push guardrail.
# See ../README.md for full docs and adapt steps.
#
# Install per-repo:
#   ln -s /absolute/path/to/pre-push.sh .git/hooks/pre-push
# Or use install.sh in this directory.
#
# Configuration is loaded from (first found wins):
#   $GUARDRAIL_CONFIG
#   ~/.config/guardrail/guardrail.config.sh
#   ./.guardrail.config.sh

set -u
RED=$'\033[31m'; YEL=$'\033[33m'; GRN=$'\033[32m'; RST=$'\033[0m'

fail() { echo "${RED}[guardrail BLOCK]${RST} $*" >&2; exit 1; }
warn() { echo "${YEL}[guardrail WARN]${RST}  $*" >&2; }
ok()   { echo "${GRN}[guardrail OK]${RST}    $*" >&2; }

# ----- Defaults (overridable in the config file) -----
SCOPE_FILTER="${SCOPE_FILTER:-github.com/your-account/}"
INTERNAL_PATTERNS="${INTERNAL_PATTERNS:-}"  # empty = block 1 disabled
_SECRET_PATTERNS_DEFAULT='(sk-[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA |OPENSSH |EC |DSA |PGP )?PRIVATE KEY-----|xoxb-[0-9]+-[0-9]+|xoxp-[0-9]+-[0-9]+)'
SECRET_PATTERNS="${SECRET_PATTERNS:-$_SECRET_PATTERNS_DEFAULT}"
_FORBIDDEN_FILES_DEFAULT='\.(mobileprovision|p12|pem|pfx|keystore|jks|env|env\.local)$|(^|/)\.npmrc$|(^|/)\.netrc$|(^|/)id_rsa$|(^|/)id_ed25519$'
FORBIDDEN_FILES="${FORBIDDEN_FILES:-$_FORBIDDEN_FILES_DEFAULT}"
MAX_BLOB_BYTES="${MAX_BLOB_BYTES:-5242880}"
# Default attack-payload patterns are assembled from fragments so this
# script file itself does not contain literal trigger strings (which
# would trip block 5 when this file is added to a guarded repo).
_ATTACK_PATTERNS_DEFAULT="(Payloads""AllTheThings|metasploit""-framework|web""shell|reverse""_shell\\.php|meter""preter|cobalt""strike)"
ATTACK_PATTERNS="${ATTACK_PATTERNS:-$_ATTACK_PATTERNS_DEFAULT}"
ENABLE_BLOCK_5_ATTACK_PATTERNS="${ENABLE_BLOCK_5_ATTACK_PATTERNS:-1}"
MAX_COMMITS_SCANNED="${MAX_COMMITS_SCANNED:-500}"
MAX_COMMITS_NEW_BRANCH="${MAX_COMMITS_NEW_BRANCH:-200}"

# Load config (last wins).
for cfg in \
    "${GUARDRAIL_CONFIG:-}" \
    "$HOME/.config/guardrail/guardrail.config.sh" \
    "./.guardrail.config.sh"; do
  [ -n "$cfg" ] && [ -f "$cfg" ] && . "$cfg"
done

remote="${1:-}"
url="${2:-}"

# ----- Scope filter: only enforce for matching remotes -----
case "$url" in
  *"$SCOPE_FILTER"*) ;;
  *) ok "remote $url not in scope ($SCOPE_FILTER) — skipping"; exit 0 ;;
esac

# ----- Resolve commit range -----
refs_payload=$(cat)
[ -z "$refs_payload" ] && { ok "no refs to push"; exit 0; }

range_list=()
while read -r local_ref local_sha remote_ref remote_sha; do
  [ "$local_sha" = "0000000000000000000000000000000000000000" ] && continue
  if [ "$remote_sha" = "0000000000000000000000000000000000000000" ]; then
    range_list+=("$local_sha" "--not" "--remotes" "--max-count=$MAX_COMMITS_NEW_BRANCH")
  else
    range_list+=("$remote_sha..$local_sha")
  fi
done <<< "$refs_payload"

[ ${#range_list[@]} -eq 0 ] && { ok "nothing new"; exit 0; }

commits=$(git rev-list "${range_list[@]}" 2>/dev/null | head -"$MAX_COMMITS_SCANNED")
[ -z "$commits" ] && { ok "no new commits to scan"; exit 0; }

# ----- Block 1: internal-string blacklist -----
if [ -n "$INTERNAL_PATTERNS" ]; then
  for sha in $commits; do
    hits=$(git show --no-color --pretty=format: "$sha" 2>/dev/null | grep -inE "$INTERNAL_PATTERNS" | head -5)
    if [ -n "$hits" ]; then
      fail "commit $sha contains internal token(s):
$hits

Scrub the commit and retry. If false positive, refine INTERNAL_PATTERNS in your guardrail config."
    fi
  done
  ok "no internal-string hits"
else
  warn "block 1 (internal-string) disabled — INTERNAL_PATTERNS empty"
fi

# ----- Block 2: secret patterns -----
for sha in $commits; do
  hits=$(git show --no-color --pretty=format: "$sha" 2>/dev/null | grep -inE "$SECRET_PATTERNS" | head -5)
  if [ -n "$hits" ]; then
    fail "commit $sha contains likely secret(s):
$hits"
  fi
done
ok "no obvious secrets"

# ----- Block 3: forbidden filenames -----
for sha in $commits; do
  files=$(git show --no-color --name-only --pretty=format: "$sha" 2>/dev/null | grep -E "$FORBIDDEN_FILES" | head -5)
  if [ -n "$files" ]; then
    fail "commit $sha touches forbidden file(s):
$files"
  fi
done
ok "no forbidden filenames"

# ----- Block 4: oversized blobs -----
for sha in $commits; do
  big=$(git diff-tree --no-commit-id -r --root "$sha" 2>/dev/null | awk '{print $4,$6}' | while read -r blob path; do
    [ "$blob" = "0000000000000000000000000000000000000000" ] && continue
    sz=$(git cat-file -s "$blob" 2>/dev/null || echo 0)
    [ "$sz" -gt "$MAX_BLOB_BYTES" ] && echo "$path ($sz bytes)"
  done | head -3)
  if [ -n "$big" ]; then
    fail "commit $sha contains oversized blob(s) > $MAX_BLOB_BYTES bytes:
$big"
  fi
done
ok "no oversized blobs"

# ----- Block 5: attack-payload fingerprints -----
if [ "$ENABLE_BLOCK_5_ATTACK_PATTERNS" = "1" ]; then
  for sha in $commits; do
    hits=$(git show --no-color --pretty=format: "$sha" 2>/dev/null | grep -inE "$ATTACK_PATTERNS" | head -3)
    if [ -n "$hits" ]; then
      fail "commit $sha references attack-payload artifact(s):
$hits"
    fi
  done
  ok "no attack-payload references"
else
  warn "block 5 (attack-payload) disabled by config"
fi

ok "all checks passed for $url"
exit 0
