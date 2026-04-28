# llm-output-sql-missing-semicolon-detector

Pure-stdlib, code-fence-aware detector that catches **SQL statements
missing their terminating `;`** inside SQL blocks an LLM emits in
markdown.

LLMs frequently produce SQL like:

```sql
CREATE TABLE users (id INT, name TEXT);
INSERT INTO users VALUES (1, 'a')
INSERT INTO users VALUES (2, 'b');
```

The middle `INSERT` has no `;`. Most SQL CLIs (psql, mysql, sqlite3)
will then either silently merge it with the next statement, raise a
confusing parse error halfway through the script, or — worst —
execute only part of the file and leave the database in a half-
migrated state. The bug is invisible to the model because there is
no parser in the loop. This detector flags it at emit time so the
output can be re-prompted before it ships to a database.

## What it flags

| kind | meaning |
|---|---|
| `missing_semicolon` | a statement begins with a recognized SQL verb at the start of a line and ends (either before the next verb-led line, or at end of block) without a terminating `;` |

Recognized verbs: `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `CREATE`,
`DROP`, `ALTER`, `WITH`, `MERGE`, `REPLACE`, `TRUNCATE`, `GRANT`,
`REVOKE`, `BEGIN`, `COMMIT`, `ROLLBACK`, `SET`, `USE`, `EXPLAIN`,
`ANALYZE`, `VACUUM`, `PRAGMA` (case-insensitive).

Recognized fence info-string tags: `sql`, `psql`, `mysql`, `sqlite`,
`sqlite3`, `postgres`, `postgresql`, `plsql`, `tsql`.

## Quote and comment handling

Before scanning, single-quoted strings (with `''` escape),
double-quoted identifiers, `--` line comments, and `/* ... */` block
comments are blanked out (preserving newlines and offsets). This
means a `;` inside a string literal or a comment is correctly ignored
when deciding whether a statement was terminated.

## Out of scope (deliberately)

- Stored-procedure bodies with nested `BEGIN ... END` blocks.
- Dialect-specific delimiter changes such as MySQL `DELIMITER //`.
- Statements that legitimately omit `;` because the dialect allows
  it as the very last statement of an interactive session.
- Full SQL grammar validation. This is a *style/safety* check, not a
  parser.

## Usage

```
python3 detect.py <markdown_file>
```

Stdout: one finding per line, e.g.

```
block=1 line=2 kind=missing_semicolon snippet='INSERT INTO users VALUES (1, ...'
```

Stderr: `total_findings=<N> blocks_checked=<M>`.

Exit codes:

| code | meaning |
|---|---|
| `0` | no findings |
| `1` | at least one finding |
| `2` | bad usage |

## Worked example

Run against the bundled `examples/bad.md` (3 missing semicolons) and
`examples/good.md` (0 findings):

```
$ python3 detect.py examples/bad.md
block=1 line=2 kind=missing_semicolon snippet="INSERT INTO users VALUES (1, 'alice')"
block=2 line=1 kind=missing_semicolon snippet='SELECT id, name FROM users WHERE id = 1'
block=3 line=1 kind=missing_semicolon snippet="UPDATE users SET name = 'carol' WHERE id"
# stderr: total_findings=3 blocks_checked=3
# exit: 1

$ python3 detect.py examples/good.md
# stderr: total_findings=0 blocks_checked=2
# exit: 0
```
