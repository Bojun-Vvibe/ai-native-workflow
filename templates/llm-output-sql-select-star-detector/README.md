# llm-output-sql-select-star-detector

## Purpose

Detect `SELECT *` (and the qualified `SELECT t.*` form) in SQL files.
Production queries should list columns explicitly so callers, query
planners, and schema evolution all stay predictable.

## Why `SELECT *` is an anti-pattern

- Pulls back every column, wasting I/O, network bandwidth, and ORM
  hydration cost — even for columns the caller never reads.
- Defeats covering-index optimizations: the planner cannot serve a
  `SELECT *` from an index that does not contain every column.
- Silently breaks downstream code when a column is added, removed,
  renamed, or has its type changed (column ordinals shift, hydration
  blows up, JSON serialization includes new fields).
- Particularly dangerous in `INSERT ... SELECT *`: a schema drift on
  either side corrupts inserts.
- Hides intent — a reader cannot tell which columns the application
  actually depends on, making refactors and dead-column detection
  much harder.

## Why LLMs emit this

- `SELECT * FROM table` is the shortest possible query and dominates
  tutorial / README / SO snippets in the training corpus.
- When the model does not know the schema, `*` is the safest-looking
  completion ("the user can sort it out later").
- Code in legacy ORM bootstrap / scaffolding tends to use `SELECT *`,
  reinforcing the pattern.

## When to use

- Reviewing LLM-generated SQL (`.sql`, `.ddl`, `.dml`) before merge.
- CI lint over a `migrations/` or `queries/` directory.
- Pre-commit lint on agent-authored SQL.

## How to run

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code is `1` if any findings, `0` otherwise. Findings print as
`path:line:col: <kind> — <snippet>`.

## What it flags

- `select-star` — bare `SELECT *`, including with `DISTINCT`, `ALL`,
  or `TOP n` modifiers.
- `select-qualified-star` — `SELECT t.*`, including when mixed with
  explicit columns (`SELECT u.*, o.id`).

## What it intentionally skips

- `SELECT COUNT(*)`, `SELECT SUM(*)`, and other aggregates where
  `*` is an aggregate-function argument, not a column-list shortcut.
- `SELECT 1`, `SELECT NULL`, `SELECT EXISTS (...)`, etc.
- `SELECT id, price * quantity AS total` — arithmetic asterisks.
- `SELECT *` text inside `--` and `/* */` comments.
- `SELECT *` text inside `'...'`, `"..."`, and backticked identifiers.

The detector is a single-pass scanner with explicit comment/string
masking, not a full SQL parser. It errs toward false negatives on
exotic dialects (recursive CTEs with unusual whitespace, `MERGE`
statements that embed sub-selects in non-standard positions) rather
than false positives on plain code.

## Files

- `detect.py` — the detector (python3 stdlib only).
- `bad/` — four SQL files that MUST trigger.
- `good/` — two SQL files that MUST NOT trigger.
- `smoke.sh` — runs the detector on `bad/` and `good/` and asserts
  bad-hits > 0 and good-hits == 0.

## Smoke output

```
$ bash smoke.sh
bad_hits=8
good_hits=0
OK: bad=8 good=0
```

## How to fix the findings

- Replace `*` with the explicit list of columns the caller actually
  reads. Yes, even if it is 12 columns long.
- For `INSERT ... SELECT *`, name both sides: `INSERT INTO t (a, b, c)
  SELECT a, b, c FROM source`.
- If you are writing an ad-hoc one-off query (not committed code),
  `SELECT *` is fine — this detector is meant for committed
  application SQL.
