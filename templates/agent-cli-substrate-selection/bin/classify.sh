#!/usr/bin/env bash
# classify.sh — pipe a task description through the substrate-classifier prompt
#
# Usage:
#   echo "summarize this PR diff" | ./bin/classify.sh
#   ./bin/classify.sh < task.txt
#   TASK="refactor utils.ts" ./bin/classify.sh
#
# Configuration (env vars, override per-invocation):
#   INSTALLED_CLIS  — comma-separated list of installed AI CLIs
#   AGENT_CMD       — command to pipe the assembled prompt into (e.g. "llm -m gpt-4o-mini")
#                     If empty, runs in dry-run mode: prints the assembled prompt and exits 0.
#   DRY_RUN_ON_NO_AGENT — 1 (default) to allow dry-run; 0 to error if AGENT_CMD is unset.

set -euo pipefail

# --- Adapt this section --------------------------------------------------------
INSTALLED_CLIS="${INSTALLED_CLIS:-llm,aichat,claude,codex,opencode}"
AGENT_CMD="${AGENT_CMD:-}"
DRY_RUN_ON_NO_AGENT="${DRY_RUN_ON_NO_AGENT:-1}"
# ------------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROMPT_PATH="${SCRIPT_DIR}/../prompts/classify.md"

if [[ ! -f "$PROMPT_PATH" ]]; then
    echo "error: classifier prompt not found at $PROMPT_PATH" >&2
    exit 2
fi

# Read TASK from env, args, or stdin.
TASK_TEXT=""
if [[ -n "${TASK:-}" ]]; then
    TASK_TEXT="$TASK"
elif [[ $# -gt 0 ]]; then
    TASK_TEXT="$*"
else
    if [[ -t 0 ]]; then
        echo "error: no TASK provided (env, args, or stdin)" >&2
        exit 2
    fi
    TASK_TEXT="$(cat)"
fi

if [[ -z "$TASK_TEXT" ]]; then
    echo "error: TASK is empty" >&2
    exit 2
fi

# Assemble the full prompt: system prompt body + concrete inputs.
ASSEMBLED=$(cat <<EOF
$(cat "$PROMPT_PATH")

---

TASK:
${TASK_TEXT}

INSTALLED_CLIS:
${INSTALLED_CLIS}
EOF
)

# Dispatch.
if [[ -z "$AGENT_CMD" ]]; then
    if [[ "$DRY_RUN_ON_NO_AGENT" == "1" ]]; then
        echo "# DRY RUN — AGENT_CMD not set; printing assembled prompt." >&2
        echo "# Configure AGENT_CMD (e.g. 'llm -m gpt-4o-mini') to actually classify." >&2
        echo "$ASSEMBLED"
        exit 0
    else
        echo "error: AGENT_CMD is unset and DRY_RUN_ON_NO_AGENT=0" >&2
        exit 2
    fi
fi

printf "%s" "$ASSEMBLED" | eval "$AGENT_CMD"
