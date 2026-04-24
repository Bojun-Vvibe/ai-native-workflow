# Template: prompt-regression-snapshot

A snapshot-test pattern for prompts. When you tweak a system
prompt, an agent profile, or a tool-call schema, you want to
know **exactly which existing eval cases changed output** —
and whether each change is an intentional improvement or a
silent regression.

This is to prompts what `git diff` is to code: a deterministic
artifact you can review, approve, or reject. It is the
companion to [`llm-eval-harness-minimal`](../llm-eval-harness-minimal/),
which scores quality. This one tracks **change**.

## Why this exists

Three failure modes the absence of snapshots produces:

1. **Silent regressions.** You shorten a system prompt to save
   tokens; one of 40 eval cases now answers the wrong question
   but its score is still "passes" because the rubric was loose.
   You don't notice for two weeks.
2. **Approval whiplash.** Without a baseline, every prompt
   tweak triggers a full re-evaluation by hand: "is this output
   better, worse, or the same as last time?" You burn an hour
   per change.
3. **Drift across forks.** Two engineers tune the same prompt
   in two branches. Each "looks fine" against the live model.
   When merged, neither knows what the other actually changed
   in observable behaviour, only in prompt text.

Snapshots fix this by separating two questions:

- **Did the output change?** Mechanically answerable by
  diffing the new run against the snapshot.
- **Is the change intentional?** Answerable only by a human,
  but only on the cases that *did* change. Cases with
  unchanged output need no review.

## What's in the box

```
prompt-regression-snapshot/
├── README.md                    # this file
├── SNAPSHOTS.md                 # snapshot format spec + workflow
├── bin/
│   ├── snapshot.py              # run fixtures, diff against snapshots, report
│   └── approve.py               # promote a flagged case to its new snapshot
└── examples/
    ├── 01-clean-diff/           # prompt change with no observable effect
    │   ├── fixtures/            # 3 fixtures
    │   └── snapshots/           # bootstrapped against prompt v1
    └── 02-flagged-regression/   # prompt change that breaks one of three cases
        ├── fixtures/
        └── snapshots/
```

When you adopt this template, copy `bin/` into your repo and
create your own `fixtures/<case-id>.json` + `snapshots/<case-id>.json`
trees. The examples are runnable as-is and serve as templates for
your own fixtures.

## When to use this template

Use it when **all** of:

- You have a stable set of inputs you trust (a fixture corpus,
  not a live traffic sample).
- Outputs are reproducible — temperature 0, fixed seed, pinned
  model version. Snapshots are meaningless against a non-
  deterministic generator.
- You change prompts often enough that "did anything change?"
  is a recurring question. If you tweak prompts twice a year,
  re-running the eval harness from scratch each time is fine.
- Your eval rubric is *coarser* than your prompt's actual
  behaviour. (If the rubric is fine-grained enough to catch
  every regression, snapshots are redundant. They almost
  never are.)

Do **not** use it for:

- Free-text creative output. Snapshots reward verbatim
  reproduction; a prompt change that produces equally-good
  but differently-worded prose is flagged as a regression
  every time. False positive city.
- Live-traffic regression detection. Use the eval harness
  with a quality rubric for that. Snapshots are for **fixtures
  you control**.
- Inputs that depend on time, randomness, or external state
  (today's date, a random ID, a live API call). The snapshot
  will go stale instantly.

## The workflow

1. **Bootstrap.** Run the harness against your current prompt
   to populate `snapshots/`. Commit those snapshots. They are
   now your baseline.
2. **Change the prompt.** Tweak the system prompt, profile,
   or tool schema.
3. **Re-run the harness.** `python3 bin/snapshot.py run`
   produces a per-case verdict: `MATCH`, `CHANGED`, or `NEW`
   (a fixture with no snapshot yet).
4. **Review only the `CHANGED` cases.** For each, decide:
   - **Intentional improvement** → `python3 bin/approve.py
     <case-id>` updates the snapshot. Commit the new snapshot
     alongside the prompt change.
   - **Silent regression** → roll back the prompt change, or
     fix it and re-run.
5. **CI gate.** A pre-merge check runs `snapshot.py run` and
   fails the build if any case is `CHANGED` *and* its snapshot
   has not been updated in the same commit. This forces every
   behavioural change to be acknowledged.

## What "match" means precisely

Two outputs match iff their **canonicalised** form is byte-equal:

- For JSON output: `json.dumps(value, sort_keys=True,
  separators=(',', ':'))`. Ignores key ordering and whitespace.
- For prose output: line-by-line equality after stripping
  trailing whitespace. (Mid-line whitespace differences DO
  count as a change — that's almost always a real prompt
  effect.)

The harness emits both representations in the report so a
reviewer can see whether the diff is structural or cosmetic.

## What's in a snapshot file

```json
{
  "case_id": "001-extract-user",
  "fixture_sha": "f1a2...",
  "prompt_sha": "abc1...",
  "model": "<your-model-id>",
  "temperature": 0,
  "captured_at": "2026-04-24T10:00:00Z",
  "output_canonical": "{\"email\":\"alice@example.com\",\"name\":\"Alice\",\"user_id\":42}",
  "output_raw": "{\n  \"user_id\": 42,\n  \"name\": \"Alice\",\n  \"email\": \"alice@example.com\"\n}"
}
```

The `prompt_sha` and `fixture_sha` matter: when either changes,
the report flags the case as `CHANGED` even if the model output
is byte-identical. This catches the "you changed the prompt but
the eval-harness wrapper happens to mask the difference" trap.

## Running the worked examples

This template ships with a deterministic mock model so the
examples are fully runnable without an API key. The mock reads
`fixture.input` and looks up a canned output in
`fixture.mock_outputs[<prompt_sha_short>]` — so you can simulate
"the prompt changed" by changing which key is used.

### Example 01: clean diff (no observable change)

```sh
cd templates/prompt-regression-snapshot
python3 bin/snapshot.py run --fixtures examples/01-clean-diff/fixtures \
                            --snapshots examples/01-clean-diff/snapshots \
                            --prompt-sha v2
```

Expected: 3/3 `MATCH`. Exit 0.

This simulates a prompt change (`v1` → `v2`) that the model is
robust against — output stays byte-identical. The snapshots
need no update.

### Example 02: flagged regression

```sh
python3 bin/snapshot.py run --fixtures examples/02-flagged-regression/fixtures \
                            --snapshots examples/02-flagged-regression/snapshots \
                            --prompt-sha v2
```

Expected: 2/3 `MATCH`, 1 `CHANGED` (case `002-summarise-pr`),
exit 1.

This simulates a prompt change that broke summary-formatting
for one case. CI would fail. Reviewer inspects the diff,
decides: intentional → `approve.py 002-summarise-pr`, or
unintentional → roll back the prompt.

## Adapt this section

Edit these to fit your stack:

- `bin/snapshot.py` — replace the `MockModel` class with your
  SDK call. Keep determinism (`temperature=0`, pinned model,
  no streaming).
- Canonicalisation rules in `_canonicalise()` — extend if your
  output format isn't JSON or plain prose (e.g. YAML, CSV).
- CI gate — add `python3 bin/snapshot.py run --strict` to your
  pre-merge job. `--strict` exits non-zero on any `CHANGED`
  case.
- Snapshot naming convention — the default `<case-id>.json`
  works for ~100 cases. Beyond that, shard into
  `snapshots/<group>/<case-id>.json`.

## When this template is overkill

- You have one prompt and three eval cases. Just re-run them
  by hand.
- Your model is non-deterministic and you have no plans to
  pin it. Snapshots will flag everything, every run, forever.
- You haven't shipped an eval harness yet. Build that first
  (use [`llm-eval-harness-minimal`](../llm-eval-harness-minimal/));
  add snapshots when prompt-tweak frequency justifies the
  ceremony.

## Composes with

- [`llm-eval-harness-minimal`](../llm-eval-harness-minimal/) —
  same fixture format. Reuse the YAML/JSON cases. Snapshots
  catch *change*; the eval harness catches *quality*.
- [`prompt-fingerprinting`](../prompt-fingerprinting/) — feeds
  the `prompt_sha` field. Use the `cache_hash` to verify
  prompt-text identity, the `semantic_hash` to spot
  intentional vs accidental changes.
- [`commit-message-trailer-pattern`](../commit-message-trailer-pattern/) —
  add `Snapshots-Updated: 002,005` trailer when a commit
  promotes snapshots, so PR reviewers can spot behavioural
  changes without re-running the harness.
- [`failure-mode-catalog`](../failure-mode-catalog/) — the
  silent-regression failure mode is exactly what this template
  prevents.

## License

MIT (see repo root).
