# Template: structured-output-repair-loop

A bounded, stuck-detecting repair loop for LLM calls that must
return structured output (JSON, YAML, a strict prose schema).
The loop validates each attempt, feeds the validator's error back
to the model as a structured hint, retries up to `max_attempts`,
and — critically — detects when the model is **stuck repeating
the same mistake** so it can either downgrade to a fallback or
fail loudly instead of burning tokens.

This is the operational generalization of the `repair_once`
policy in [`agent-output-validation`](../agent-output-validation/).
Where that template gives you a *one-shot* repair, this one gives
you the *loop*: bounded attempts, stuck-detection, degradation
strategy, and per-attempt cost/latency accounting.

## Why this exists

A naive structured-output loop looks like this:

```python
while True:
    out = call_model(prompt)
    try:
        return parse(out)
    except ValidationError:
        prompt = prompt + "\nPrevious output was invalid. Try again."
```

This burns tokens forever in three failure modes:

1. **The schema is wrong** — the model literally cannot satisfy
   it (you asked for a UUID but show examples with integer IDs).
   The loop runs `max_attempts` times then errors anyway.
2. **The model is stuck** — every retry produces the same
   invalid shape (e.g. always emits a markdown code fence around
   the JSON because that's what the system prompt rewards). You
   pay N times for one mistake.
3. **The error message is too vague** — `"Previous output was
   invalid"` doesn't tell the model *what to fix*, so it
   regenerates randomly instead of diffing.

This template gives you a loop that:

- Feeds the **specific** validator error back as a structured
  hint (`json_pointer` to the offending field, expected vs
  actual type, allowed enum values).
- Fingerprints each attempt's error so it can detect *same
  mistake twice* and either degrade or abort early.
- Caps attempts via `max_attempts` and total elapsed time via
  `deadline_ms`.
- Records per-attempt cost so you can budget for it (a 4-attempt
  loop on a 2k-token prompt is 8k+ tokens — not free).

## What's in the box

```
structured-output-repair-loop/
├── README.md                       # this file
├── LOOP.md                         # the algorithm: states, transitions, exit conditions
├── bin/
│   ├── repair_loop.py              # reference implementation, stdlib only, mock model
│   ├── error_fingerprint.py        # canonical error → stable hash for stuck-detection
│   └── render_hint.py              # validator error → structured hint block
├── prompts/
│   ├── system.md                   # system-prompt fragment that opts the model into the contract
│   └── repair-turn.md              # user-turn template for an N>1 attempt
└── examples/
    ├── 01-typo-field/              # model misspelled "user_id" as "userId"; 1 repair fixes it
    ├── 02-stuck-loop/              # model keeps wrapping JSON in ```json fences; stuck after 2
    └── 03-degraded-fallback/       # max_attempts hit; falls back to free-text + manual parse
```

## When to use this template

Use it when **all** of:

- The downstream caller needs structured output (JSON, YAML,
  CSV with strict columns, a prose template with required
  sections).
- The model is allowed to fail validation occasionally
  (i.e. it's not a one-shot pre-agency CLI where you'd rather
  fail fast).
- You can afford 2–4× the base call cost in the worst case.
- You want **bounded** worst-case behaviour: never burn more
  than `max_attempts` calls, never run past `deadline_ms`.

Do **not** use it for:

- Streaming output you can't replay. The loop assumes you can
  run the call again from the start.
- Pure-prose generation. There's nothing to validate; you'd
  just be retrying randomly.
- Calls that are *already* deterministic (temp=0, structured
  output mode pinned by the SDK). Either it works first try
  or it never will. Use a single attempt + hard error.

## The loop algorithm

See [`LOOP.md`](LOOP.md) for the full state machine. Summary:

```
state = { attempt: 1, errors_seen: [], started_at: now() }
while attempt <= max_attempts and elapsed() < deadline_ms:
    out = call_model(prompt)                                 # attempt N
    try:
        return ok(parse(out), attempts=attempt, status="parsed")
    except ValidationError as e:
        fp = fingerprint(e)
        if fp in state.errors_seen:
            # Same mistake twice — model is stuck.
            return degrade(out, attempts=attempt, status="stuck", error=e)
        state.errors_seen.append(fp)
        prompt = render_repair_turn(prompt, original_out=out, error=e)
        attempt += 1
return degrade(last_out, attempts=attempt, status="exhausted", error=last_e)
```

Two non-obvious bits:

1. **Fingerprinting collapses noise.** A `ValidationError` like
   `"users.0.email: not a string"` and `"users.1.email: not a
   string"` fingerprint to the same hash (`json_pointer-pattern
   + error-class`), because they're the same mistake on two
   array elements. We don't want to count that as "two distinct
   errors made progress" — it's one mistake.
2. **Degradation is not failure.** The `degrade(...)` call lets
   the caller decide: hard-fail, return the last raw output for
   manual inspection, or fall back to a separate (cheaper)
   pre-agency parse. Example 03 shows the fallback path.

## Per-attempt hint block

The `render_hint.py` helper turns a validator error into a
hint block the next attempt sees. Format:

```
=== REPAIR REQUIRED ===
Previous attempt failed validation:
  path:     /users/0/email
  error:    expected string matching ^[^@]+@[^@]+\.[^@]+$
  got:      "not-an-email"
  fix:      Replace the value at /users/0/email with a valid RFC 5322 address.

Reproduce ALL fields from the previous attempt EXCEPT the one
above. Do not change other fields. Do not add explanatory prose.
=== END REPAIR ===
```

The "reproduce all fields except" instruction matters. Without
it the model often regenerates from scratch and *introduces new
errors* in fields that were previously fine.

## Stuck-detection: what counts as the same error

`error_fingerprint.py` derives a hash from:

- **Error class** (`SchemaValidationError`,
  `JSONDecodeError`, `EnumViolation`, …)
- **JSON pointer normalised** (`/users/0/email` →
  `/users/*/email`; array indices collapse to `*`)
- **Expected type / pattern** (verbatim)

It deliberately does **not** include:

- Actual offending value (so `"not-an-email"` and
  `"also-not-email"` count as the same mistake).
- Line/column numbers from the parser.
- Timestamp of the failure.

This is the right granularity for "is the model stuck": same
field, same expectation, same class of mistake → stuck.

## Worked examples

Each example is a deterministic mock-model run against
`repair_loop.py`. No real API call needed. Run any of them:

```sh
cd templates/structured-output-repair-loop
python3 bin/repair_loop.py examples/01-typo-field/scenario.json
```

Each example ships:

- `scenario.json` — input prompt, schema, mock model script
  (a list of canned outputs the mock returns in order).
- `expected.txt` — the loop's exit state (status, attempts,
  fingerprints seen).

| Example | What goes wrong | Loop outcome |
|---|---|---|
| `01-typo-field` | Attempt 1 emits `userId` (camelCase) but schema requires `user_id`. Hint pinpoints the field; attempt 2 fixes it. | `status=parsed, attempts=2` |
| `02-stuck-loop` | Model wraps JSON in ```json fences three attempts in a row — same fingerprint twice triggers stuck-detection on attempt 2. | `status=stuck, attempts=2` |
| `03-degraded-fallback` | Model keeps emitting an unrequested top-level `notes` field through 4 attempts. Loop exhausts; caller falls back to a regex-based field stripper. | `status=exhausted, attempts=4, fallback=stripped_notes_field` |

## Cost model

Worst case for a loop with `max_attempts=4` and a base prompt
of `T_base` input tokens, `T_out` output tokens per attempt:

```
total_input_tokens  = T_base + 3 * (T_base + T_out + T_hint)
total_output_tokens = 4 * T_out
```

The per-attempt hint block is small (~80 tokens) but the
*previous attempt's output* is replayed in the repair turn
so the model can see what it produced. That's where the
quadratic-ish growth comes from. If `T_out` is large (e.g. a
1000-line JSON), prefer `max_attempts=2` and degrade aggressively.

## Composes with

- [`agent-output-validation`](../agent-output-validation/) —
  this loop is the policy implementation behind the `repair_once`
  → `repair_loop` upgrade path.
- [`tool-call-retry-envelope`](../tool-call-retry-envelope/) —
  if the structured output is a *tool argument*, the dedup
  envelope guarantees the side effect doesn't fire on every
  repair attempt; only the validated final attempt commits.
- [`failure-mode-catalog`](../failure-mode-catalog/) — this
  template's stuck-detection is the operational fix for the
  "Schema Drift" and "Premature Convergence" entries.
- [`token-budget-tracker`](../token-budget-tracker/) — log each
  attempt with `phase=repair_loop`, `attempt=N`, so the report
  surfaces missions where the loop is the budget hog.

## Adapt this section

Edit these to fit your stack:

- `bin/repair_loop.py` — replace the mock-model interface
  (`MockModel.complete()`) with your SDK's call. Keep the loop
  body unchanged.
- `prompts/system.md` — append your project's house style
  (output language, units, etc.) so the model isn't reformatting
  on every repair turn.
- `bin/error_fingerprint.py` — extend `_normalise_pointer()` if
  your schema uses keys (not indices) for collections (e.g.
  `/configs/redis/host` → `/configs/*/host`).
- `LOOP.md` — set `max_attempts` and `deadline_ms` defaults to
  match your latency SLO.

## When this template is overkill

If your call site is one of:

- A single `extract_field()` against gpt-4o where the SDK's
  built-in `response_format=json_schema` already enforces the
  shape — let the SDK handle it. Don't add a loop on top.
- A nightly batch where you'd rather fail fast and fix the
  prompt by hand — one attempt, hard error, alert.

…skip this template. Pay the loop only when *graceful
degradation* is worth more than *fail fast*.

## License

MIT (see repo root).
