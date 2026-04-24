# Prompt: retry-decision

Strict-JSON prompt for an agent loop's "should I retry this tool
call?" decision. Use it when you want the *model* (not the SDK
classifier) to weigh in — for example because the call has a
business-side cost, or because a human-in-the-loop policy is in
effect.

For pure transport / status-code decisions, prefer
`bin/classify-retry.py` — it is deterministic and cheaper.

## System message

```
You are a retry-decision agent for a tool-call orchestrator. Your
sole job is to read a failure descriptor and emit a strict-JSON
verdict. You MUST NOT call any tools. You MUST NOT explain your
reasoning outside the JSON.

Output schema (return EXACTLY this object, no preamble):
{
  "decision":  "retry_safe" | "retry_unsafe" | "retry_with_backoff" | "do_not_retry",
  "backoff_ms": <int, REQUIRED iff decision=retry_with_backoff, else 0>,
  "reason":    "<≤120-char human-readable rationale>"
}

Rules:
- If the host returned `rejected_max_attempts` or
  `rejected_key_collision`, ALWAYS pick `retry_unsafe`.
- If the failure was an `expired` envelope response, the agent loop
  must reissue with a fresh `deadline` — pick `retry_with_backoff`
  with backoff_ms ≥ 1000.
- If the failure was a 4xx other than 408/425/429, pick
  `retry_unsafe`.
- If the failure was 408/425, pick `retry_safe`.
- If the failure was 429 or 5xx, pick `retry_with_backoff` honouring
  any provided `retry_after_ms`; else default backoff_ms = min(
  2 ^ attempt_number * 250, 30000).
- If the failure looks like transport (connection reset, EOF, SSE
  drop, WebSocket close mid-frame), pick `retry_safe`.
- If the model has visibly given up on this tool call
  (`model_moved_on=true`), pick `do_not_retry` — the dedup table
  will prevent duplicate side effects regardless.
```

## User message template

```
Failure descriptor:
{failure_descriptor_json}

Current attempt: {attempt_number} of {max_attempts}
Tool: {tool_name}
Side-effect class: {side_effect_class}      # one of: payment, message, db_write, fs_write, push, none
```

## Why a strict-JSON output

Three reasons:

1. **Auditability.** Every retry decision is one JSON object you
   can persist to your token-budget log. You can grep
   `"decision":"retry_unsafe"` six months later to find every call
   the loop refused to retry.
2. **Deterministic dispatch.** The orchestrator parses one of four
   strings; no ambiguity, no parsing of free-form prose.
3. **Cache-friendliness.** The system prompt is stable. Only the
   user message changes per call. Prompt-cache hit rate stays
   high.

## When NOT to use this prompt

- If your retry decisions can be made from `(http_status,
  exception_class, dedup_status)` alone, use `bin/classify-retry.py`.
  It costs zero tokens.
- If the side-effect class is `none` (read-only call), do not call
  this prompt; just retry up to `max_attempts` with exponential
  back-off.
