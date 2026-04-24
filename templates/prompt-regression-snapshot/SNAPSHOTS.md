# SNAPSHOTS.md — format and workflow

## Snapshot file format

One JSON file per case under `snapshots/<case-id>.json`:

```json
{
  "case_id": "001-extract-user",
  "fixture_sha": "f1a2...",          // sha256 of the fixture file
  "prompt_sha": "abc1...",           // caller-supplied prompt identity
  "model": "<your-model-id>",
  "temperature": 0,
  "captured_at": "ISO8601 UTC",
  "output_canonical": "<canonical form, byte-comparable>",
  "output_raw": "<as-emitted, for human review>"
}
```

`captured_at` is the only field that's not part of the equality
check. It's there for forensics ("when did we last bless this
output?"), not for matching.

## Three-state verdict

After a run, every case is in exactly one of:

| Verdict | Meaning | Exit-code contribution |
|---|---|---|
| `MATCH` | New output canonicalises byte-equal to snapshot. | 0 |
| `CHANGED` | New output canonicalises differently from snapshot. | 1 (in `--strict` mode) |
| `NEW` | Fixture has no snapshot yet (first time seen). | 0 unless `--strict-new` |
| `MISSING` | Snapshot exists but no fixture (orphan). | 1 (always — orphans rot fast) |

The `MISSING` verdict catches the "I deleted the fixture but
forgot the snapshot" cleanup miss.

## When the prompt changes

`prompt_sha` is supplied by the caller (`--prompt-sha v2`) or
derived from a `prompts/` directory hash. When it changes:

- Cases with **same model output** still verdict `MATCH`. The
  snapshot's `prompt_sha` is updated in place during the next
  approval (or by `bin/snapshot.py rebless --no-output-change`).
- Cases with **different model output** verdict `CHANGED`. The
  reviewer either approves (new snapshot captures both new
  prompt_sha and new output) or rolls back.

This is the right behaviour: a prompt change that produces
unchanged output is interesting (good!) but doesn't need
explicit human approval. Only **observable** changes do.

## Approval workflow

```sh
# Run, see one CHANGED case.
python3 bin/snapshot.py run

# Inspect the diff (printed by `run`; also via `diff` subcommand).
python3 bin/snapshot.py diff 002-summarise-pr

# Decide: intentional? Approve.
python3 bin/snapshot.py approve 002-summarise-pr

# Now the snapshot file on disk is updated.
git diff snapshots/002-summarise-pr.json
git add snapshots/002-summarise-pr.json prompts/...
git commit -m "feat(prompt): tighten summary format

Snapshots-Updated: 002-summarise-pr"
```

## CI gate

A pre-merge job:

```yaml
- name: prompt regression check
  run: python3 templates/prompt-regression-snapshot/bin/snapshot.py run --strict
```

`--strict` exits non-zero on any `CHANGED` case whose snapshot
has not been updated in the same commit. The build fails until
the human either approves the change (and commits the new
snapshot) or rolls back the prompt.

## What snapshots do NOT replace

- **Eval rubrics** — snapshots tell you output changed, not
  whether the new output is *better*. Pair with
  `llm-eval-harness-minimal`.
- **Live monitoring** — snapshots run on fixtures, not
  production traffic. Pair with whatever tracing you have for
  the live distribution.
- **Schema validation** — the snapshot doesn't care if the
  output is *valid*, only if it changed. Pair with
  `agent-output-validation` and/or `structured-output-repair-loop`.
