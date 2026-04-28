# llm-output-sql-string-concat-injection-detector

Flags Python code where SQL queries are built via **string concatenation**,
**`%`-formatting**, **`.format()`**, or **f-strings** and then handed to a
DB cursor's `execute()` / `executemany()` / `executescript()`. These are
the canonical SQL-injection vectors that LLM-generated data-access code
loves to emit.

## What it catches

```python
cur.execute("SELECT * FROM users WHERE name = '" + name + "'")    # concat
cur.execute("UPDATE u SET email = '%s' WHERE id = %d" % (e, uid)) # %
cur.execute("DELETE FROM orders WHERE status = '{}'".format(s))   # .format
cur.execute(f"SELECT * FROM products WHERE c = '{cat}' LIMIT {n}")# f-string
```

Replace with parameterized queries:

```python
cur.execute("SELECT * FROM users WHERE name = ?", (name,))
```

## What it deliberately ignores

- `cur.execute("SELECT 1")` — fully literal SQL, no interpolation.
- `cur.execute(sql, (a, b))` where `sql` is a name binding (we only flag
  the call site when the *query argument expression itself* is dynamic).
- Strings without an SQL keyword (SELECT/INSERT/UPDATE/DELETE/CREATE/
  DROP/ALTER/REPLACE/MERGE) — avoids false positives on log lines etc.

## Usage

```
python3 detector.py <file.py | file.md> [<file> ...]
```

It accepts both `.py` files and Markdown files (it extracts ` ```python `
fenced blocks and scans them with the original line numbers preserved).

## Exit codes

| code | meaning              |
|------|----------------------|
| 0    | no findings          |
| 1    | findings reported    |
| 2    | usage / read error   |

## Smoke test

```
$ python3 templates/llm-output-sql-string-concat-injection-detector/detector.py \
    templates/llm-output-sql-string-concat-injection-detector/examples/bad/queries.py
templates/.../examples/bad/queries.py:8:  dynamic SQL passed to execute() — use parameterized queries (cursor.execute(sql, params))
templates/.../examples/bad/queries.py:15: dynamic SQL passed to execute() — use parameterized queries (cursor.execute(sql, params))
templates/.../examples/bad/queries.py:21: dynamic SQL passed to execute() — use parameterized queries (cursor.execute(sql, params))
templates/.../examples/bad/queries.py:27: dynamic SQL passed to execute() — use parameterized queries (cursor.execute(sql, params))
templates/.../examples/bad/queries.py:34: dynamic SQL passed to executemany() — use parameterized queries (cursor.executemany(sql, params))
exit=1   # 5 findings

$ python3 .../detector.py .../examples/good/queries.py
exit=0   # 0 findings
```

## Implementation notes

- Pure `python3` stdlib. Uses `ast` for the Python scan and a tiny
  fence-state machine for Markdown. No third-party deps.
- Heuristic, not a theorem prover: it asks "is the first arg of
  `execute()` a *string built dynamically* AND does the literal portion
  look like SQL?" That catches the common LLM failure mode without
  drowning in false positives.
- Line numbers in Markdown findings are mapped back to the source
  Markdown file, not the offset inside the fence.
