#!/usr/bin/env bash
# End-to-end test for pre-push.sh.
# Builds a throwaway repo, attempts pushes that should pass and fail
# each block, and asserts the right outcome.
#
# Run: bash test/test-guardrail.sh
#
# Notes:
#   - The "push" is simulated by invoking pre-push.sh directly with the
#     remote URL and synthetic stdin payload. A real `git push` would
#     fail because there's no real remote.
#   - Working directory is a fresh temp dir; nothing in your real repos
#     is touched.

set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/pre-push.sh"
PASS=0; FAIL=0
RED=$'\033[31m'; GRN=$'\033[32m'; RST=$'\033[0m'

assert_blocks() {
  local label="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    echo "${GRN}PASS${RST} $label (exit=$actual)"
    PASS=$((PASS+1))
  else
    echo "${RED}FAIL${RST} $label (expected exit=$expected, got $actual)"
    FAIL=$((FAIL+1))
  fi
}

run_hook() {
  # $1 = remote URL, $2 = local sha, $3 = remote sha (or 0...)
  local url="$1" lsha="$2" rsha="$3"
  printf "refs/heads/main %s refs/heads/main %s\n" "$lsha" "$rsha" \
    | "$HOOK" origin "$url" >/dev/null 2>&1
  echo $?
}

# Set up throwaway repo
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cd "$TMP"
git init -q -b main
git config user.email "test@example.com"
git config user.name "Test User"

# Override config so block 1 is active with a known pattern
export GUARDRAIL_CONFIG="$TMP/.gconf.sh"
cat > "$GUARDRAIL_CONFIG" <<'EOF'
SCOPE_FILTER="github.com/test-account/"
INTERNAL_PATTERNS='(SECRET_INTERNAL_CODENAME|internal\.example\.net)'
ENABLE_BLOCK_5_ATTACK_PATTERNS=1
EOF

URL_IN_SCOPE="https://github.com/test-account/test-repo.git"
URL_OUT="https://github.com/other-account/other-repo.git"

ZERO="0000000000000000000000000000000000000000"

# ---------- Test 1: clean commit, in scope -> pass ----------
echo "ok content" > a.txt
git add a.txt && git commit -q -m "init clean"
SHA1=$(git rev-parse HEAD)
assert_blocks "T1 clean commit in scope" 0 "$(run_hook "$URL_IN_SCOPE" "$SHA1" "$ZERO")"

# ---------- Test 2: out-of-scope remote -> always pass ----------
echo "anything" > b.txt
git add b.txt && git commit -q -m "anything"
SHA2=$(git rev-parse HEAD)
assert_blocks "T2 out-of-scope remote bypasses" 0 "$(run_hook "$URL_OUT" "$SHA2" "$SHA1")"

# ---------- Test 3: internal pattern -> block ----------
echo "this references SECRET_INTERNAL_CODENAME oops" > c.txt
git add c.txt && git commit -q -m "leak"
SHA3=$(git rev-parse HEAD)
assert_blocks "T3 internal-pattern blocks" 1 "$(run_hook "$URL_IN_SCOPE" "$SHA3" "$SHA2")"

# ---------- Test 4: secret pattern -> block ----------
git reset -q --hard "$SHA2"
# Build a synthetic secret-shaped string at runtime so the literal does not
# appear in this file (which would itself trip block 2 when *this* repo is pushed).
FAKE_KEY="sk-$(printf 'abcdefghijklmnopqrstuvwxyz1234567890')"
echo "key=$FAKE_KEY" > secret.txt
git add secret.txt && git commit -q -m "secret"
SHA4=$(git rev-parse HEAD)
assert_blocks "T4 secret-pattern blocks" 1 "$(run_hook "$URL_IN_SCOPE" "$SHA4" "$SHA2")"

# ---------- Test 5: forbidden filename -> block ----------
git reset -q --hard "$SHA2"
echo "FOO=bar" > .env
git add .env && git commit -q -m "dotenv"
SHA5=$(git rev-parse HEAD)
assert_blocks "T5 .env filename blocks" 1 "$(run_hook "$URL_IN_SCOPE" "$SHA5" "$SHA2")"

# ---------- Test 6: oversized blob -> block ----------
git reset -q --hard "$SHA2"
dd if=/dev/zero of=big.bin bs=1m count=6 2>/dev/null
git add big.bin && git commit -q -m "big"
SHA6=$(git rev-parse HEAD)
assert_blocks "T6 oversized blob blocks" 1 "$(run_hook "$URL_IN_SCOPE" "$SHA6" "$SHA2")"

# ---------- Test 7: attack-payload reference -> block ----------
git reset -q --hard "$SHA2"
# Build the trigger string at runtime so the literal does not appear
# in this test file (which would itself trip block 5 in the parent repo).
ATTACK_TRIGGER="Payloads""AllTheThings"
echo "see $ATTACK_TRIGGER repo for examples" > notes.md
git add notes.md && git commit -q -m "notes"
SHA7=$(git rev-parse HEAD)
assert_blocks "T7 attack-payload reference blocks" 1 "$(run_hook "$URL_IN_SCOPE" "$SHA7" "$SHA2")"

echo
echo "== summary: $PASS passed, $FAIL failed =="
[ "$FAIL" = 0 ]
