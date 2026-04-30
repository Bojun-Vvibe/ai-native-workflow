# llm-output-go-fmt-sprintf-sql-query-detector

Static detector for the Go anti-pattern of building a SQL query string
with `fmt.Sprintf` (or `fmt.Fprintf`/`+` concatenation) and then
passing the formatted string into a `database/sql` execution method
(`Query`, `QueryRow`, `Exec`, `QueryContext`, `QueryRowContext`,
`ExecContext`, `Prepare`).

This is a classic LLM SQL-injection footgun:

```go
q := fmt.Sprintf("SELECT * FROM users WHERE name = '%s'", name)
rows, err := db.Query(q)
```

The correct pattern is parameterized queries with placeholders:

```go
rows, err := db.Query("SELECT * FROM users WHERE name = $1", name)
```

## What this flags

Two related shapes:

1. **Direct call shape** — `db.Query(fmt.Sprintf(...))`,
   `tx.Exec(fmt.Sprintf(...))`,
   `conn.QueryRowContext(ctx, fmt.Sprintf(...))`, etc. The detector
   recognizes any method named one of: `Query`, `QueryRow`, `Exec`,
   `Prepare`, `QueryContext`, `QueryRowContext`, `ExecContext`,
   `PrepareContext`. The first SQL argument (after an optional
   `context.Context`) must be a `fmt.Sprintf(...)` or
   `fmt.Sprint(...)` call, **and** the format string of that
   `Sprintf` must contain a SQL keyword (`SELECT`, `INSERT`,
   `UPDATE`, `DELETE`, `MERGE`, `WITH`, `REPLACE`, `CREATE`).
2. **String-concat shape** — same execution methods, but the SQL
   argument is a `+` concatenation involving a Go string literal that
   contains a SQL keyword and at least one non-literal operand (a
   variable, field access, or function call). This catches the
   `db.Query("SELECT ... WHERE id = " + id)` form.

A finding is suppressed if the same logical line carries the marker
`// llm-allow:sprintf-sql-query`. Lines inside `//` line comments,
`/* ... */` block comments, and Go raw/regular string literals are
not scanned for the trigger pattern (so a docstring example does not
fire).

The detector also extracts fenced `go` code from Markdown.

## CWE references

* **CWE-89**: Improper Neutralization of Special Elements used in an
  SQL Command (SQL Injection).
* **CWE-564**: SQL Injection — Hibernate.
* **CWE-943**: Improper Neutralization of Special Elements in Data
  Query Logic.

## Usage

```
python3 detect.py <file_or_dir> [...]
```

Exit code `1` on any findings, `0` otherwise. python3 stdlib only.

## Worked example

```
$ bash verify.sh
bad findings:  7 (rc=1)
good findings: 0 (rc=0)
PASS
```

See `examples/bad/` and `examples/good/` for the concrete fixtures.
