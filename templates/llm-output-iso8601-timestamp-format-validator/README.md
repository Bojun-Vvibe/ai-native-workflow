# `llm-output-iso8601-timestamp-format-validator`

Pure stdlib consistency gate for ISO-8601 timestamps inside an LLM
output blob. Catches the bug class where the model silently mixes
`2026-04-26T10:00:00Z`, `2026-04-26 10:00:00`, `2026-04-26T10:00`, and
`04/26/2026 10:00:00` inside the same status report / audit log /
changelog. Each style is *technically* parseable; the resulting text
is not safely diffable, sortable, or copy-pasteable into a downstream
tool that expects one canonical form.

Five finding kinds:

- `mixed_timezone_style` — more than one of `{Z, +HH:MM offset, naive}`
  appears. Reported once per **minority** occurrence so the caller can
  grep them out.
- `mixed_separator` — some timestamps use `T` between date and time,
  others use a literal space.
- `seconds_precision_drift` — some timestamps include `:SS`, others
  omit.
- `fractional_seconds_drift` — some timestamps include `.fff`, others
  omit (independent of the `:SS` axis).
- `non_iso_date_shape` — a timestamp-looking token whose date portion
  is not `YYYY-MM-DD` (e.g. `04/26/2026 10:00:00`). Always flagged,
  not subject to the minority rule.

"Minority" = the less common of two styles in the document. Ties break
by reporting the **second**-encountered style. If only one style is
present on an axis, the detector emits nothing for that axis: this is
a **consistency** gate, not a style enforcer.

## When to use

- Pre-publish gate on any LLM-generated **status report / audit log /
  release note / changelog** where downstream tools will sort or diff
  the rendered text.
- Pre-commit guardrail on LLM-drafted **runbooks / postmortems** —
  mixed timezone styles in an incident timeline cause real
  miscommunication.
- Audit step in a **review-loop** that promotes
  [`agent-output-validation`](../agent-output-validation/)'s
  `repair_once` policy: a `mixed_timezone_style` finding feeds the
  exact offending offset back into the repair prompt.
- Cron-friendly: findings are sorted by `(offset, kind, raw)`, so
  byte-identical output across runs makes diff-on-the-output a valid
  CI signal.

## Inputs / outputs

```
validate_timestamps(text: str) -> list[Finding]

Finding(kind: str, offset: int, raw: str, detail: str)
```

- `text` — the LLM output to scan. Must be `str` (raises
  `ValidationError` otherwise).
- Returns the list of findings sorted by `(offset, kind, raw)`.
- `format_report(findings)` renders a deterministic plain-text report.

Pure function: no I/O, no clocks, no calendar lookups. The detector
**does not** parse timestamps into `datetime` objects or check whether
a given date is real (Feb 30 etc.) — that's a separate concern. It
only enforces **shape consistency**.

## Composition

- [`agent-output-validation`](../agent-output-validation/) — feed a
  finding's `offset` and `kind` into the repair prompt for a one-turn
  fix; this template is the validator behind the `repair_once` policy
  for prose outputs.
- [`structured-output-repair-loop`](../structured-output-repair-loop/) —
  the per-attempt validator inside the loop's `validate(attempt)`
  callback; minority-style fingerprints make a stuck loop detectable
  (same `kind` + same `raw` across attempts → bail).
- [`agent-tool-call-timestamp-monotonicity-validator`](../agent-tool-call-timestamp-monotonicity-validator/) —
  orthogonal: that template validates monotonic ordering of trace
  spans, this validates surface-form consistency in prose. Run both
  on a status report that interleaves narrative and trace timestamps.
- [`structured-error-taxonomy`](../structured-error-taxonomy/) —
  classifies as `do_not_retry / attribution=model` for `non_iso_date_shape`
  (model invented a non-ISO date — has to be regenerated, not retried).

## Worked example

```
$ python3 example.py
```

Verbatim output:

```
=== 01-clean ===
input: 'Run started at 2026-04-26T10:00:00Z and ended at 2026-04-26T10:05:00Z.'
OK: timestamp format is consistent.

=== 02-mixed-timezone ===
input: 'Tick A 2026-04-26T10:00:00Z, tick B 2026-04-26T10:01:00Z, tick C 2026-04-26T10:02:00Z, tick D 2026-04-26T10:03:00 (no tz).'
FOUND 1 timestamp finding(s):
  [mixed_timezone_style] offset=94 raw=2026-04-26T10:03:00 :: style=naive; counts={'z_suffix': 3, 'naive': 1}

=== 03-mixed-separator ===
input: 'Started 2026-04-26T10:00:00Z then 2026-04-26T10:01:00Z then 2026-04-26 10:02:00Z (space sep).'
FOUND 1 timestamp finding(s):
  [mixed_separator] offset=60 raw=2026-04-26 10:02:00Z :: style=space; counts={'T': 2, 'space': 1}

=== 04-seconds-precision-drift ===
input: 'Bucket 2026-04-26T10:00:00Z 2026-04-26T10:01:00Z 2026-04-26T10:02:00Z 2026-04-26T10:03Z (no seconds).'
FOUND 1 timestamp finding(s):
  [seconds_precision_drift] offset=70 raw=2026-04-26T10:03Z :: style=no_sec; counts={'with_sec': 3, 'no_sec': 1}

=== 05-non-iso-date ===
input: 'Mission ran on 04/26/2026 10:00:00 according to the host log.'
FOUND 1 timestamp finding(s):
  [non_iso_date_shape] offset=15 raw=04/26/2026 10:00:00 :: date portion is not YYYY-MM-DD

```

Notes:

- Case 02 catches the lone naive timestamp out of four `Z`-suffix
  ticks — `counts={'z_suffix': 3, 'naive': 1}` makes the majority
  obvious in the report.
- Case 03 catches the single space-separator timestamp. Note the
  space-separator timestamp *also* carries `Z`, so it does **not**
  trip the timezone axis — these axes are independent.
- Case 04 catches the seconds-omitted token. Note `2026-04-26T10:03Z`
  is parseable ISO-8601, but mixing it with `:SS` siblings makes the
  document non-uniform.
- Case 05 catches the US-style `MM/DD/YYYY` outright — no minority
  rule applies since the date portion isn't ISO at all.

## Files

- `validator.py` — pure stdlib detector + `format_report`
- `example.py` — five-case worked example
