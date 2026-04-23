#!/usr/bin/env bash
# examples/test-guardrail.sh
#
# Runnable end-to-end test of the pre-commit guardrail plugin.
#
# What it does:
#   1. Creates a temporary git repo in a scratch directory.
#   2. Writes a fixture file containing a fake-but-realistic-looking secret.
#   3. Stages the file (simulating an agent about to commit).
#   4. Invokes the plugin's guardrail logic against the staged diff.
#   5. Asserts the guardrail BLOCKS the commit and exits non-zero.
#   6. Cleans up.
#
# Exit codes:
#   0  test passed (guardrail correctly blocked the leaky commit)
#   1  test failed (guardrail let it through, or something else went wrong)
#
# Requirements: bash, git, node (>= 18). No network.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_PATH="${SCRIPT_DIR}/../plugin.example.js"

if [ ! -f "${PLUGIN_PATH}" ]; then
  echo "FAIL: plugin not found at ${PLUGIN_PATH}" >&2
  exit 1
fi

# ---- Build a tiny harness that runs the plugin's guardrail ----------------
# The plugin exports { hooks: { "before:git-commit": fn } }. The hook receives
# a context with .abort(reason). We synthesize a minimal context, capture the
# abort reason if any, and exit accordingly.

TMP="$(mktemp -d -t guardrail-test.XXXXXX)"
trap 'rm -rf "${TMP}"' EXIT

cd "${TMP}"
git init -q .
git config user.email "test@example.invalid"
git config user.name "Guardrail Test"

# ---- Fixture: a fake leaky file ------------------------------------------
# The literal below is a synthetic test value, not a real key. It matches the
# OpenAI-style sk- shape that the plugin's SECRET_PATTERNS catches. Hyphens
# in the body keep it from tripping common upstream secret scanners that
# require a contiguous alphanumeric run.

cat > leaked.config.js <<'EOF'
// Fixture for guardrail test. Not a real credential.
module.exports = {
  apiKey: "sk-test-fake-not-real-1234",
};
EOF

git add leaked.config.js

# ---- Run the harness ------------------------------------------------------

HARNESS_OUTPUT="$(node -e '
  const plugin = require(process.argv[1]);
  let aborted = false;
  let reason = "";
  const ctx = { abort: (r) => { aborted = true; reason = r; } };
  plugin.hooks["before:git-commit"](ctx);
  if (aborted) {
    console.log("BLOCKED:" + reason);
    process.exit(0);
  } else {
    console.log("ALLOWED");
    process.exit(0);
  }
' "${PLUGIN_PATH}")" || {
  echo "FAIL: harness errored" >&2
  exit 1
}

# ---- Assert ---------------------------------------------------------------

case "${HARNESS_OUTPUT}" in
  BLOCKED:*)
    echo "PASS: guardrail blocked the leaky commit"
    echo "      reason: ${HARNESS_OUTPUT#BLOCKED:}"
    exit 0
    ;;
  ALLOWED)
    echo "FAIL: guardrail allowed a commit containing a fake secret" >&2
    exit 1
    ;;
  *)
    echo "FAIL: unexpected harness output: ${HARNESS_OUTPUT}" >&2
    exit 1
    ;;
esac
