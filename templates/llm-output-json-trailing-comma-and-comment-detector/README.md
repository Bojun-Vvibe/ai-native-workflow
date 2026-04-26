# llm-output-json-trailing-comma-and-comment-detector

Pure-stdlib detector for **JSONC artifacts** that leak into output
that is supposed to be strict JSON: trailing commas before `]` / `}`,
and `//` line / `/* … */` block comments.

This is the single most common reason a model's "JSON" reply fails
`json.loads` despite parsing fine in a JSONC-tolerant linter
(`jsonc-parser`, VS Code's settings parser, JSON5, hjson). It deserves
its own focused detector rather than being a generic "json invalid"
branch, because:

1. The **fix is mechanical**. Strip the comments, trim the comma. A
   one-shot repair prompt with the exact offset is much cheaper than
   asking the model to re-emit the whole document.
2. **Distinguishing JSONC drift from real schema violations** prevents
   the repair loop from chasing the wrong bug. If `repair_count` keeps
   firing on `,}` patterns the right fix is system-prompt tuning
   ("strict JSON only — no comments, no trailing commas"), not
   harder schema validation.
3. The **lexer is small** (~150 lines, one pass, string-aware) and
   has no external dependency. A real JSON parser will reject the
   whole document and tell you nothing useful about *which* of the
   four artifacts is present where.

The detector is **lexer-only**, not a parser. It walks the input
once, tracks whether we are inside a string (with backslash escaping
honored), and reports artifacts with line + column + offset.

## Detected kinds

| Kind | What | Notes |
|---|---|---|
| `trailing_comma_object` | `,}` (with optional whitespace) | The classic; v0.1 schemas often emit this. |
| `trailing_comma_array` | `,]` (with optional whitespace) | Same root cause as the object form. |
| `line_comment` | `// …` to end of line | Trained-on-TypeScript signal. |
| `block_comment` | `/* … */` | Often used for "removed in vN" annotations. |
| `unterminated_block_comment` | `/*` with no closing `*/` | **Never auto-repair.** Reject the whole document. |

## API

```python
from validator import detect_jsonc_artifacts, format_report, strip_artifacts

findings = detect_jsonc_artifacts(text)
print(format_report(findings))

# Optional one-shot mechanical repair (returns cleaned, findings):
cleaned, _ = strip_artifacts(text)
obj = json.loads(cleaned)   # caller still validates schema
```

`strip_artifacts` is **opt-in** and refuses to touch input containing
an `unterminated_block_comment` — that case is a partial / torn
output and should escalate to a re-emit, not a guess.

Each `Finding` carries `offset`, `line_no`, `column`, `kind`, and a
short literal `snippet` (newlines / tabs escaped) so the report
itself is a single line per finding and pipes cleanly through
`grep` / `awk`. Findings are sorted by `offset` so byte-identical
re-runs make diff-on-the-output a valid CI signal.

## Worked example

`example.py` exercises eight cases — five "model emitted JSONC"
shapes, an in-string false-positive negative test, an
unterminated-comment torn-output test, and a kitchen-sink case with
all four kinds in one document. Run it directly:

```
python3 example.py
```

Captured output (verbatim):

```
=== case 01 strict-clean JSON ===
OK: no JSONC artifacts found.

=== case 02 trailing comma in object ===
FOUND 1 JSONC artifact(s):
  line 1 col 25 offset 24: kind=trailing_comma_object ',}'
--- after strip_artifacts ---
{"id": 42, "name": "foo"}
json.loads OK -> keys=['id', 'name']

=== case 03 trailing comma in array ===
FOUND 1 JSONC artifact(s):
  line 1 col 19 offset 18: kind=trailing_comma_array ',]'
--- after strip_artifacts ---
{"items": [1, 2, 3]}
json.loads OK -> keys=['items']

=== case 04 // line comment ===
FOUND 1 JSONC artifact(s):
  line 2 col 3 offset 4: kind=line_comment '// human-friendly note'
--- after strip_artifacts ---
{
  
  "ok": true
}
json.loads OK -> keys=['ok']

=== case 05 /* block comment */ between fields ===
FOUND 1 JSONC artifact(s):
  line 1 col 10 offset 9: kind=block_comment '/* removed for v2 */'
--- after strip_artifacts ---
{"a": 1,  "b": 2}
json.loads OK -> keys=['a', 'b']

=== case 06 the kitchen sink ===
FOUND 5 JSONC artifact(s):
  line 2 col 3 offset 4: kind=line_comment '// header'
  line 4 col 20 offset 44: kind=block_comment '/* was 5 */'
  line 5 col 22 offset 77: kind=trailing_comma_array ',]'
  line 5 col 24 offset 79: kind=trailing_comma_object ',\n  }'
  line 6 col 4 offset 84: kind=trailing_comma_object ',\n}'
--- after strip_artifacts ---
{
  
  "cfg": {
    "retries": 3,  
    "tags": ["x", "y"]
  }
}
json.loads OK -> keys=['cfg']

=== case 07 comma-comment lookalike inside a string is NOT a finding ===
OK: no JSONC artifacts found.

=== case 08 unterminated block comment ===
FOUND 1 JSONC artifact(s):
  line 1 col 9 offset 8: kind=unterminated_block_comment '/* oops where does this '
```

What the cases prove:

- **01** — strict-clean JSON passes silently. No false positives on
  punctuation that is not preceded by a comma artifact.
- **02 / 03** — both trailing-comma flavors are reported with the
  correct kind and the offset *of the comma* (not the bracket), so a
  `text[:offset] + text[offset+1:]` patch is one line. The cleaned
  text round-trips through `json.loads` with the expected keys
  (proof in the captured output).
- **04** — line comments are reported with the correct line / column.
  After stripping, the bracketed key set survives (`['ok']`); the
  trailing whitespace where the comment used to be is left in place
  (we never touch whitespace — preserving line numbers in the
  cleaned text matters for downstream error reporting).
- **05** — block comments between fields are reported with full
  delimiter snippet (`/* removed for v2 */`) and stripping leaves
  a parse-clean two-key object.
- **06** — the kitchen-sink case proves all four kinds report
  independently in offset order. Notice the **two** distinct
  `trailing_comma_object` findings (one after `]`-followed-by-comma,
  one at the document end) and the `trailing_comma_array` between
  them — the lexer does not over- or under-count when artifacts are
  adjacent. The cleaned text is one `json.loads` away from a usable
  config dict.
- **07** — the critical negative test. A comma and a `/* … */`
  lookalike *inside* a JSON string value (`"SELECT a, /* not a real
  comment */ b FROM t WHERE x = 3,"`) produce **zero** findings.
  This is the test the naïve `text.replace(",}", "}")` approach
  always fails — and why this template ships a string-aware lexer
  rather than a regex. Backslash-escaped quotes inside strings are
  honored too (the validator handles `\\` and `\"` in strings).
- **08** — an unterminated block comment is reported as
  `unterminated_block_comment`. `strip_artifacts` deliberately
  refuses to repair this case — the input is partial / torn and the
  correct action is to re-emit, not to guess where `*/` was meant to
  go. The case prints no `--- after strip_artifacts ---` block,
  proving the refusal.

## Composition

- **`structured-output-repair-loop`** — a `repair_count == 1` failure
  whose findings are entirely from this detector should be rewritten
  through `strip_artifacts` rather than re-prompted. The repair turn
  is byte-deterministic (no model call), so it doesn't count against
  the model-repair budget.
- **`agent-output-validation`** — feed `(kind, line_no, column)` into
  the schema-repair prompt for a one-turn fix when the model has to
  re-emit. The same prompt shape (`"remove the trailing comma at
  line 5 col 22"`) works for any of the four kinds.
- **`structured-error-taxonomy`** — `trailing_comma_*` and
  `*_comment` are `retryable_after_repair / attribution=model`; the
  model is emitting a slightly-wrong dialect, not failing. An
  `unterminated_block_comment` is `retryable_after_repair / attribution=upstream`
  (output was truncated mid-emission — see
  `partial-json-tail-recovery`).
- **`partial-json-tail-recovery`** — runs *before* this detector when
  the upstream report says the stream was cut. This detector
  presupposes a complete document; recovery presupposes truncation.
  Wire them in that order and a torn JSONC document still produces a
  usable parse.
- **`agent-decision-log-format`** — log a single line per repair
  decision: `repair_kind=jsonc_strip, artifacts=5, model_call=false`
  so cost reports can attribute mechanical repairs separately from
  re-prompts.

## Tuning

- **No knobs on by default.** Strict JSON is the assumption; if your
  pipeline wants JSON5 / hjson / JSONC output, you don't need this
  detector.
- For a pipeline that *does* tolerate comments but not trailing
  commas (rare but real — JSON-with-comments-only dialects), filter
  the `Finding` list before reporting:
  `[f for f in findings if f.kind not in ("line_comment", "block_comment")]`.
  No detector flag for this — keeping the API one-axis is the design.
