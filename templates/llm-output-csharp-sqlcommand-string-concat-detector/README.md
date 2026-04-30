# llm-output-csharp-sqlcommand-string-concat-detector

Static detector for the C# / ADO.NET anti-pattern of building a SQL
query by string concatenation, `$"..."` interpolation, or
`string.Format` and then handing the resulting string to a
`SqlCommand` (or sibling) constructor or `CommandText` property.

This is the C# version of the classic SQL-injection footgun an LLM
loves to emit:

```csharp
var cmd = new SqlCommand("SELECT * FROM users WHERE name = '" + name + "'", conn);
// or
cmd.CommandText = $"SELECT * FROM users WHERE name = '{name}'";
// or
cmd.CommandText = string.Format("SELECT * FROM users WHERE id = {0}", id);
```

The correct pattern is parameterized commands:

```csharp
var cmd = new SqlCommand("SELECT * FROM users WHERE name = @name", conn);
cmd.Parameters.AddWithValue("@name", name);
```

## What this flags

Two related shapes:

1. **Constructor shape** — `new SqlCommand(<sql>, ...)` (or any of
   `OracleCommand`, `OleDbCommand`, `OdbcCommand`, `SQLiteCommand`,
   `MySqlCommand`, `NpgsqlCommand`) where the first argument is one
   of:
   * a `+` concatenation of a string literal containing a SQL keyword
     and at least one non-literal operand;
   * a `$"..."` / `$@"..."` interpolated string containing a SQL
     keyword **and** at least one `{...}` placeholder;
   * a `string.Format(...)` call whose first argument contains a SQL
     keyword.
2. **Property shape** — `<ident>.CommandText = <expr>;` where `<expr>`
   matches any of the three sub-shapes above.

SQL keywords recognized: `SELECT`, `INSERT`, `UPDATE`, `DELETE`,
`MERGE`, `WITH`, `REPLACE`, `CREATE`, `DROP`, `ALTER`, `TRUNCATE`.

A finding is suppressed if the same logical line carries
`// llm-allow:sqlcommand-concat`. Comments and string literal interiors
are masked before pattern matching, so docstring examples don't fire.

The detector also extracts fenced `cs` / `csharp` code blocks from
Markdown.

## CWE references

* **CWE-89**: Improper Neutralization of Special Elements used in an
  SQL Command (SQL Injection).
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

See `examples/bad/` and `examples/good/` for fixtures.
