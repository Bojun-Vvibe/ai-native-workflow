#!/usr/bin/env bash
# run-checklist.sh — pipe a unified diff into a configured agent CLI
# with the four-question structural checklist prompt.
#
# Usage:
#   git diff origin/main...HEAD | run-checklist.sh
#   gh pr diff 1234 --repo owner/repo | run-checklist.sh
#
# Configuration (env vars, all optional):
#   AGENT_CMD   — command that reads a prompt on stdin and emits
#                 the response on stdout. Defaults to printing the
#                 assembled prompt and exiting 0 (dry-run mode), so
#                 the script is safe to demo without an LLM
#                 configured. Examples:
#                   AGENT_CMD="claude -p"
#                   AGENT_CMD="codex exec"
#                   AGENT_CMD="opencode run"
#   PROMPT_FILE — path to the prompt template. Defaults to
#                 ../prompts/agent-checklist.prompt.md relative to
#                 this script.
#
# Exit codes:
#   0 — no high-risk findings (or dry-run mode)
#   1 — at least one question fired at "Bug-shape risk: high"
#   2 — usage error (no diff on stdin)
#
# This script is intentionally small. It does no diff parsing of
# its own — it trusts the agent to follow the prompt's output
# format. If the agent drifts, you'll see that in the output and
# can re-run; the script does not try to repair drifted output.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROMPT_FILE="${PROMPT_FILE:-${SCRIPT_DIR}/../prompts/agent-checklist.prompt.md}"
AGENT_CMD="${AGENT_CMD:-}"

if [ -t 0 ]; then
  echo "error: no diff on stdin" >&2
  echo "usage: git diff origin/main...HEAD | $(basename "$0")" >&2
  exit 2
fi

if [ ! -f "$PROMPT_FILE" ]; then
  echo "error: prompt file not found: $PROMPT_FILE" >&2
  exit 2
fi

# Read the diff once into memory so we can both check it's
# non-empty and append it to the prompt.
DIFF_CONTENT="$(cat)"
if [ -z "$DIFF_CONTENT" ]; then
  echo "error: stdin diff is empty" >&2
  exit 2
fi

# Assemble the full prompt: template + diff.
PROMPT="$(cat "$PROMPT_FILE")"
FULL_PROMPT="${PROMPT}
${DIFF_CONTENT}"

if [ -z "$AGENT_CMD" ]; then
  # Dry-run mode: emit the assembled prompt and exit 0. Useful for
  # CI demos and for piping into your own agent harness.
  echo "$FULL_PROMPT"
  exit 0
fi

# Live mode: run the agent and inspect its output for high-risk
# findings. We tee to stdout so the reviewer always sees the full
# response, then grep separately for the exit-code signal.
RESPONSE_FILE="$(mktemp -t pr-review-checklist.XXXXXX)"
trap 'rm -f "$RESPONSE_FILE"' EXIT

echo "$FULL_PROMPT" | eval "$AGENT_CMD" | tee "$RESPONSE_FILE"

if grep -q "Bug-shape risk: high" "$RESPONSE_FILE"; then
  exit 1
fi
exit 0
