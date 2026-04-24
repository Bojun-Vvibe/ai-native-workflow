# Template: agent-trace-redaction-rules

A deterministic, allowlist-driven rule engine for redacting agent
traces, tool-call logs, and curated datasets **before** they leave
the agent's trust boundary. The rules say *what is allowed to escape*
(by JSON pointer + value class), not *what to block*. Anything not
named in the allowlist is replaced with a `[REDACTED:<reason>]`
sentinel.

This template is the trace/dataset-export counterpart to
`tool-call-retry-envelope`'s `IDENTITY_FIELDS` allowlist. That
template uses an allowlist to derive *idempotency keys* deterministically;
this one uses the same shape of allowlist to decide what is safe to
write into a trace store, an eval dataset, or a public reproduction.

## Why this exists

Three failure modes that show up the moment agent traces start being
collected centrally or shared across teams:

1. **Blocklist rot.** "Redact anything matching `re.compile(r'sk-[A-Za-z0-9]{32,}')`" works
   until the next provider ships a key that doesn't match the regex.
   Blocklists fail open. Allowlists fail closed.
2. **Contextual leak through nested fields.** A tool-call argument
   like `{"customer": {"email": "...", "internal_note": "..."}}` is
   redacted at the top level but the nested `internal_note` survives
   because the redactor only walked one level. Pointer-anchored rules
   fix this.
3. **Dataset poisoning by tool output.** A `web.fetch` tool returns
   the entire page including a `Set-Cookie` header. The trace gets
   curated into an eval dataset. Three months later the dataset is
   shared with a contractor and the cookie is in it. An export-time
   allowlist catches this once, at the boundary, instead of asking
   every dataset consumer to re-redact.

The rule engine is small (~120 lines, stdlib only) so it can sit
inline in a tracing exporter, a dataset curation script, or a CLI
filter.

## When to use

- You are exporting agent traces / tool-call logs to any store you
  do not fully trust (third-party APM, contractor laptop, public
  reproduction).
- You are curating eval datasets from production traces and want to
  guarantee the dataset cannot contain anything outside an explicit
  allowlist.
- You want a single source of truth that a security reviewer can
  read in one sitting.

## When NOT to use

- You only need to scrub one well-known field (e.g., `password`).
  Use a one-line `pop`, not a rule engine.
- The trace destination is fully inside your trust boundary and the
  data class is already known-safe (e.g., model-only telemetry with
  no tool I/O).
- You need cryptographic guarantees (sealed envelopes, signed
  redaction proofs). This template is plaintext + sentinels; pair it
  with envelope encryption if you need more.

## What's in the box

| File | What it does |
|---|---|
| `RULES.md` | The rule schema: pointer syntax, value classes, sentinels, sentinel-format guarantees, anti-patterns |
| `bin/redact.py` | Reference engine: load rules, walk a JSON document, emit redacted copy + a redaction report |
| `bin/check_rules.py` | Lints a rule file: duplicate pointers, ambiguous globs, value-class typos |
| `prompts/rule-author.md` | Strict-JSON prompt for proposing new rules from a sample trace; emits `proposed_rules` + `unmatched_paths` |
| `examples/01-allowlist-blocks-leak/` | Worked example: tool-call envelope with an unlisted `internal_note` field is redacted; report enumerates each redaction |
| `examples/02-nested-fields-with-pointer/` | Worked example: dataset record with three nested levels; pointer-anchored rules let through `meta.cost.tokens_in` while redacting sibling `meta.cost.user_id` |

## Adapt this section

Edit `rules.json` in your repo:

- `allow` — a list of `{pointer, value_class, reason}` entries
- `value_class` — one of: `int`, `float`, `bool`, `string_short`
  (≤ 64 chars, no whitespace runs), `string_enum:<set>`, `iso8601`,
  `sha256`, `passthrough` (any JSON; use sparingly)
- `pointer` — RFC 6901 JSON pointer with `*` as a single-segment
  wildcard (e.g., `/messages/*/role`)

Then run `python bin/redact.py rules.json input.json output.json`.
The exit code is non-zero if any redaction occurred and `--strict`
is passed (useful in CI: "no rule means no field exits the boundary
silently").

## Worked-example summary

| Example | Input shape | Allow rules | Result |
|---|---|---|---|
| 01-allowlist-blocks-leak | tool-call envelope `{idempotency_key, attempt_number, args:{to, body, internal_note}}` | `args.to` (string_short), `args.body` (passthrough), `idempotency_key` (sha256), `attempt_number` (int) | `internal_note` → `[REDACTED:not_in_allowlist]`; report cites pointer `/args/internal_note`, value-class observed `string_short` |
| 02-nested-fields-with-pointer | dataset record with `meta.cost.{tokens_in, tokens_out, user_id}` plus `messages[*].{role, content}` | `meta.cost.tokens_in` (int), `meta.cost.tokens_out` (int), `messages/*/role` (string_enum: user\|assistant\|system), `messages/*/content` (passthrough) | `meta.cost.user_id` → `[REDACTED:not_in_allowlist]`; one off-enum role `tool` → `[REDACTED:value_class_mismatch]` |

Both are deterministic. Re-running on the same input + same rules
produces byte-identical output.

## Cross-references

- `tool-call-retry-envelope` — shares the allowlist-shape pattern
  (`IDENTITY_FIELDS` for keys, `allow` here for traces). Both fail
  closed.
- `agent-output-validation` — runs *before* the agent acts; this
  runs *after*, on the trail.
- `failure-mode-catalog` — operational fix for "Trace Leak" and
  "Dataset Poisoning by Tool Output".
- `prompt-fingerprinting` — the `cache_hash` and `semantic_hash`
  fields produced there are typically allowlisted at `passthrough`
  in trace exports because they are by construction non-identifying.
