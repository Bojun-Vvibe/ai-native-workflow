# tool-result-size-limiter

Pure, byte-budgeted size cap for **tool call results before they enter
the agent's next-turn context**. Returns the original payload when it
already fits; on overflow, emits a head + tail "truncation sandwich"
with an inline marker line that names the bytes elided and a 12-char
sha256 prefix of the elided middle.

Stdlib-only. Pure: never mutates input. Deterministic: same input
always produces the same output. Composes downstream of any tool
runner that may produce wide-variance output sizes (file reads, log
tails, search results, HTTP bodies, shell stdout) and upstream of the
prompt assembler.

## Why bytes, not tokens

Tokens are model-specific and require a tokenizer at runtime. Bytes
are universal, are what the prompt assembler ultimately costs in
disk and wire, and are within ~25% of token count for natural-language
text — close enough for a *guardrail*, which is what this is. Use a
tokenizer-aware budget for *generation* limits; use this for *input*
guardrails.

## Two complementary mechanisms

* **Whole-payload byte cap.** If the UTF-8 encoding of the result
  fits under `max_bytes`, the result is returned verbatim — no marker
  is added. A small "ok\\n" never gets adorned.
* **Head + tail sandwich.** Above the cap, the limiter keeps
  `head_ratio` of `max_bytes` from the start and the remainder from
  the end, joined by a single marker line of the form
  `\\n…<TRUNCATED:N bytes elided of M total, sha256=HEX12>…\\n`. The
  sha256 prefix is over the *elided middle*, so two truncations of
  the same hidden payload are diff-able by humans without exposing
  contents.

UTF-8 boundary safety: head and tail are clipped on a UTF-8 character
boundary (never mid-codepoint) so the result is always valid UTF-8
even when the budget falls inside a multi-byte sequence — important
because the agent will re-encode the prompt and a half-codepoint will
either crash the encoder or produce a `U+FFFD` substitution that
makes the truncation marker harder to recognise.

## When to use

* A `read_file` tool that occasionally returns a 4 MB minified bundle.
* A `shell` tool whose stdout can be a 200k-line log tail.
* An `http_get` tool used against an unfamiliar endpoint.
* Any place where one outlier tool result can blow the prompt budget
  for the *rest* of the conversation.

## When NOT to use

* Already-structured JSON results — prefer schema-aware shrinking
  (drop fields, paginate) so the agent still gets a parseable
  document. Truncating JSON in the middle produces garbage.
* Outputs the agent must read in full to make a correctness claim
  ("does this file contain X?"). Either narrow the tool (`grep`
  instead of `read`) or chunk explicitly with the agent in the loop.
* Generation outputs from an LLM. Use `model-output-truncation-detector`
  there — the failure mode is different (incomplete generation, not
  oversized input).

## Composes with

* `tool-call-result-validator` — run validation *first* so a
  malformed-and-huge result is rejected before truncation hides the
  shape of the malformation.
* `structured-log-redactor` — redact *before* truncation so a
  secret in the elided middle is still hashed by the redactor's
  pattern set, not just absorbed into the sha-prefix marker.
* `tool-result-cache` — cache the **truncated** result, not the
  original, so cache hits and live calls present the agent with
  identical-looking output (otherwise truncation marker drift
  defeats prompt-cache prefix matching downstream).

## Inputs / outputs

`limit_tool_result(text, *, max_bytes, head_ratio=0.6) -> LimitResult`

* `text: str` — the tool result to size-cap.
* `max_bytes: int` — total UTF-8 byte budget for the returned text,
  including the marker. Must be `>= 64`.
* `head_ratio: float` — fraction of the budget for the head slice;
  remainder (minus a ~120-byte marker reservation) goes to the tail.
  Must be in `(0.0, 1.0)`. Default `0.6` favours the head because
  most CLI/log output is more diagnostic at the top.

`LimitResult` fields: `text`, `original_bytes`, `output_bytes`,
`truncated`, `elided_bytes`, `elided_sha256_prefix`. The
`elided_sha256_prefix` is the empty string when `truncated=False`.

## Worked example

`worked_example.py` runs three scenarios end-to-end.

* **Small payload** — 36 bytes against a 1 KiB cap. Returned
  verbatim, `truncated=False`, no marker added.
* **Big log dump** — ~5.4 KiB log capped to 512 bytes. Head and tail
  are both real log lines, marker reports `4968 bytes elided of 5360
  total` with a stable sha256 prefix.
* **Multi-byte UTF-8** — 600 bytes of `あ` (each 3 bytes) capped to
  200 bytes. Output is valid UTF-8: head and tail are clean
  codepoint-aligned slices, never mid-sequence.

### Verbatim stdout

```
--- small payload (fits) ---
  truncated      : False
  original_bytes : 36
  output_bytes   : 36
  elided_bytes   : 0
  elided_sha     : (n/a)
  text           : 'ok\nfound 3 matches in src/router.py\n'

--- big log (truncated) ---
  truncated      : True
  original_bytes : 5360
  output_bytes   : 464
  elided_bytes   : 4968
  elided_sha     : f3f75c5f1b78
  text[:80]      : '2026-04-25T10:00:00Z INFO request_id=abc-123 latency_ms=42 ok=true\n2026-04-25T10'
  text[-80:]     : 's=42 ok=true\n2026-04-25T10:00:00Z INFO request_id=abc-123 latency_ms=42 ok=true\n'

--- utf-8 boundary ---
  truncated      : True
  original_bytes : 600
  output_bytes   : 220
  elided_bytes   : 450
  elided_sha     : 7e2e26cb7743
  text           : 'ああああああああああああああああああああああああああああああああああああああああ\n…<TRUNCATED:450 bytes elided of 600 total, sha256=7e2e26cb7743>…\nああああああああああ'

utf-8 round-trip OK on all three scenarios.
```

The big-log output is 464 bytes (under the 512 cap, the marker plus
sandwich consumed only 464). The UTF-8 case produces a string whose
head and tail each end / begin on full `あ` characters; no `U+FFFD`
appears.
