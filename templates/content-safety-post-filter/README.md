# content-safety-post-filter

Pure, deterministic post-filter that sits between an LLM's reply and the
caller / downstream tool. Routes each output to one of four actions —
`allow` / `redact` / `review` / `block` — using a closed category enum
and a fixed severity order.

## Why

Pre-filters (`prompt-injection-prefilter`, `prompt-pii-redactor`) only
gate **input**. They cannot catch a model that:

- hallucinates a PII-shaped string the user never typed,
- echoes a system-prompt secret because instruction-following degraded
  late in a long conversation,
- generates first-person threat language unprompted, or
- pastes a private key it "remembered" from training data.

The post-filter is the last deterministic layer between the model and the
real world. It is intentionally pure (no I/O, no clocks) so it is
replayable from a JSONL trace and snapshot-testable.

## Interface

- `Rule(pattern, category, action, label)` — regex + category + verdict.
  Constructor raises `PolicyConfigError` on unknown category, unknown
  action, empty label, or invalid regex.
- `Policy(rules, block_message=…)` — ordered `Rule` collection. Empty
  rule tuple raises (a zero-rule policy silently allows everything).
  Duplicate labels raise (otherwise log queries by label silently merge).
- `evaluate(text, policy) -> Decision` — pure function.
- `Decision(action, tripped, hits, redacted_text, chosen_rule_label)`.
- `default_policy()` — conservative starter policy. Fork and tune.

## Categories (closed enum)

`self_harm`, `violence_threat`, `sexual_minor`, `hate_targeted`,
`secrets_leak`, `pii_email`, `pii_phone`, `private_key`.

Adding a new category requires editing `ALLOWED_CATEGORIES` — silent
typos in a YAML policy file are the most common safety regression, and
the closed enum makes them impossible.

## Severity order (fixed, NOT input order)

```
block > review > redact > allow
```

A `review` rule listed before a `block` rule **must not** demote the
decision. The engine picks the most severe action across all hits;
ties at the same severity break by rule order in the policy (so a more
specific rule earlier wins when authors want it to).

## Redaction stability

Redacted tokens are `<REDACT:CATEGORY:N>` where `N` is per-category and
**stable per distinct (category, matched value)** within one call. So:

```
"email a@x.com or a@x.com"  ->  "email <REDACT:PII_EMAIL:1> or <REDACT:PII_EMAIL:1>"
"email a@x.com or b@x.com"  ->  "email <REDACT:PII_EMAIL:1> or <REDACT:PII_EMAIL:2>"
```

This matters for two reasons:

1. **Prompt-cache discipline** — feeding redacted text back into the
   model preserves identity ("the same email appears twice") without
   leaking the value, and cache keys stay stable across rotations.
2. **Snapshot tests don't flap** — same input redacts identically.

## When to use

- Every model reply that goes to an end-user, a tool dispatch, or a log
  store you do not fully trust.
- Especially: tool outputs whose content the model is about to quote
  back verbatim (a model that "summarises" a curl response can leak
  the bearer token it saw in the headers).

## When NOT to use

- For **input** scrubbing — use `prompt-pii-redactor` (covers more
  PII shapes and rehydrates after the model replies).
- For semantic / paraphrased leakage detection — regex is structural,
  not semantic. Pair with a small classifier model for paraphrase
  defense if your threat model needs it.
- As your only safety layer — this is the *last* layer, not the only
  layer. See `Composes with` below.

## Composes with

- `prompt-pii-redactor` / `tool-output-redactor` — inbound; this is
  outbound. Run both.
- `llm-output-trust-tiers` — a `block` here forces the trust router to
  `quarantine` regardless of the rest of the evidence record.
- `prompt-canary-token-detector` — a canary leak is itself a
  `secrets_leak`-class violation (add a per-call canary rule at the
  edge of the policy).
- `agent-decision-log-format` — `Decision.as_log_row()` returns the
  shape that drops straight into the step log.
- `tool-output-redactor` — when a tool output passes through, redact
  PII *before* the model sees it; this filter catches what the model
  *re-emits* on the way back out.

## Run

```
python3 worked_example.py
```

## Example output

```
======================================================================
content-safety-post-filter :: worked example
======================================================================

policy           : 7 rules
allowed_categories: ['hate_targeted', 'pii_email', 'pii_phone', 'private_key', 'secrets_leak', 'self_harm', 'sexual_minor', 'violence_threat']

[clean_response]
  action       : allow
  tripped      : []
  n_hits       : 0
  chosen_rule  : None

[pii_redaction]
  action       : redact
  tripped      : ['pii_email', 'pii_phone']
  n_hits       : 3
  chosen_rule  : email_address
  redacted     : 'Contact <REDACT:PII_EMAIL:1> or <REDACT:PII_PHONE:1>. Backup contact is also <REDACT:PII_EMAIL:1>.'

[secrets_leak_block]
  action       : block
  tripped      : ['secrets_leak']
  n_hits       : 2
  chosen_rule  : aws_access_key_id_shape

[private_key_block]
  action       : block
  tripped      : ['private_key']
  n_hits       : 1
  chosen_rule  : pem_private_key_block

[severity_review_beats_redact]
  action       : review
  tripped      : ['pii_email', 'self_harm']
  n_hits       : 2
  chosen_rule  : self_harm_first_person

[severity_block_beats_review]
  action       : block
  tripped      : ['self_harm', 'violence_threat']
  n_hits       : 2
  chosen_rule  : violence_first_person_threat

[policy_config_errors_caught]
  unknown_category     -> unknown category: 'not_a_real_category' (allowed: ['hate_tar
  invalid_regex        -> invalid regex in rule 'bad_regex': unterminated character se
  empty_policy         -> Policy with zero rules: refusing to construct. An empty poli
  duplicate_label      -> duplicate rule labels: ['dup']

----------------------------------------------------------------------
Invariants:
  clean -> allow                                    OK
  pii   -> redact, stable tokens, repeated->same    OK
  fake-AWS-shaped string -> block                   OK
  fake-PEM-shaped block  -> block                   OK
  review beats redact, block beats review           OK
  4 policy-config bugs caught at construction       OK

DONE.
```

(The fake AWS / GitHub PAT / PEM strings used in the worked example
are constructed at runtime by string concatenation so this directory
contains no literal secrets — guardrail-safe.)
