# tool-output-redactor

Deterministic redactor that runs *between* a tool call's output and the model's next prompt. Replaces secrets, PII, and host-leaking paths with stable tokens (`<EMAIL_1>`, `<BEARER_1>`, `<HOME_PATH_2>`) so the model can still reason about identity and recurrence without ever seeing the raw value.

## Purpose

When a tool returns text (`ls -la`, `curl -v`, a SQL query result, a log tail), that text is usually fed straight back into the model's next turn. Three things go wrong:

1. **Secret echo.** The model paraphrases the tool output and reproduces the API key in its next message, where it lands in transcript logs and (if the user copies the message) in chat history.
2. **Host fingerprinting.** Absolute paths like `/home/alice/projects/svc` cause the model to learn operator-specific layout and emit non-portable suggestions.
3. **PII in eval store.** Every prompt-response pair tends to land in the eval / replay store. Raw emails, IPs, and tokens being there is a compliance problem.

Stripping the values entirely loses information ("the same email appeared three times" is a fact the model needs). Hashing loses readability. **Stable token mapping** keeps the structure (`<EMAIL_1>` vs `<EMAIL_2>`, repeated mentions resolve to the same token) without ever exposing the value.

## When to use

- Any agent loop where tool output goes back into the model's context.
- Any pre-eval / pre-trace-store scrubbing pipeline.
- Prompt-cache key derivation: redact first, then hash, so the cache key is not invalidated by a rotated token.

## When NOT to use

- High-stakes redaction for legal / medical compliance — use a vendored, audited library, not a 60-line stdlib regex set.
- Binary tool output (images, audio).
- When the *value itself* is what the model needs to act on (e.g. "validate this JWT signature" — but in that case, do it in a tool, not the model).

## Anti-patterns

- **Redacting non-deterministically.** A redactor that uses a fresh random ID per call breaks prompt-cache keys and makes traces un-diffable. The stable map here is intentional.
- **Redacting after the model sees it.** Redaction belongs at the tool-output boundary, not at the trace-write boundary. By the time you're scrubbing logs, the secret has already been in the model's context window.
- **Trusting the model to redact itself in a system prompt.** It will mostly comply, then fail on the one turn that matters.
- **One global pattern list shared across tenants / projects.** Allow `extra_patterns` per call site so each tool can add its own (e.g. internal-hostname patterns).
- **Catching false positives by removing patterns.** Prefer over-redacting. A `<EMAIL_1>` where there was no email is harmless; a leaked key is not.

## Files

| File | Purpose |
|---|---|
| `redactor.py` | `Redactor` class + `RedactionReport`. Stdlib-only regex; pattern order is significant (specific before generic). |
| `example.py` | Three scenarios: filesystem listing, curl debug output, repeated identifier. Plus an idempotency check. |

## Worked example

Run:

```
python3 templates/tool-output-redactor/example.py
```

Real stdout:

```
=== scenario 1: filesystem listing ===
--- original ---
total 24
-rw-r--r--  1 alice  staff  120 Apr  1 09:00 /home/alice/projects/svc/config.yaml
-rw-r--r--  1 alice  staff   88 Apr  1 09:01 /home/alice/projects/svc/.env
drwxr-xr-x  3 alice  staff   96 Apr  1 09:02 /home/alice/projects/svc/src
--- redacted ---
total 24
-rw-r--r--  1 alice  staff  120 Apr  1 09:00 <HOME_PATH_1>
-rw-r--r--  1 alice  staff   88 Apr  1 09:01 <HOME_PATH_2>
drwxr-xr-x  3 alice  staff   96 Apr  1 09:02 <HOME_PATH_3>
--- RedactionReport(total=3, HOME_PATH=3) ---

=== scenario 2: curl debug ===
--- original ---
> GET /v1/users HTTP/1.1
> Host: api.example.com
> Authorization: Bearer xoxp-FAKE-EXAMPLE-TOKEN-do-not-use-1234567890
< HTTP/1.1 200 OK
{"id":42,"email":"alice@example.com","admin_email":"ops@example.com"}
--- redacted ---
> GET /v1/users HTTP/1.1
> Host: api.example.com
> Authorization: <BEARER_1>
< HTTP/1.1 200 OK
{"id":42,"email":"<EMAIL_1>","admin_email":"<EMAIL_2>"}
--- RedactionReport(total=3, BEARER=1, EMAIL=2) ---

=== scenario 3: repeated IP ===
--- original ---
Connecting to db at 10.0.5.42 ... ok
Replicating from 10.0.5.42 to 10.0.5.43 ... ok
Verified primary 10.0.5.42 is healthy.
--- redacted ---
Connecting to db at <IPV4_1> ... ok
Replicating from <IPV4_1> to <IPV4_2> ... ok
Verified primary <IPV4_1> is healthy.
--- RedactionReport(total=4, IPV4=4) ---

=== idempotency check ===
redact(redact(x)) == redact(x): True
second-pass report: RedactionReport(none)
```

What to notice:

- **Scenario 1**: each path becomes a distinct token because they are distinct strings. If the same path repeated, it would re-use its label.
- **Scenario 2**: the bearer token *and* both emails are caught; the model still sees there are two distinct emails.
- **Scenario 3**: `10.0.5.42` is the same string in three places, so it gets one stable label `<IPV4_1>`. The model can still reason "the primary is the one we connected to."
- **Idempotency**: `redact(redact(x)) == redact(x)`. Safe to put in a pipeline that may run twice.

## Integration notes

- **Prompt cache keys.** Redact first, then derive the cache key (see `prompt-cache-key-canonicalizer`). A rotated bearer token must not invalidate the cache.
- **Trace store.** Write the redacted text to traces; keep the original only in a short-lived in-memory buffer if you need it for the immediate retry.
- **Persistent mode.** Pass `persistent=True` for a long-running session where the same DB hostname legitimately recurs across calls and you want one token across the whole transcript. Default per-call scope is safer.
- **Adding patterns.** `Redactor(extra_patterns=[("INTERNAL_HOST", r"\b\w+\.corp\.example\.net\b")])`. Order matters: specific patterns first.
