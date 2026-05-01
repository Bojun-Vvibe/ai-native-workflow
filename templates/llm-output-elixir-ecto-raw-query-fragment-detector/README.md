# llm-output-elixir-ecto-raw-query-fragment-detector

Detect raw-SQL injection sinks in LLM-emitted Elixir / Ecto code.

## Why

LLMs writing Elixir DB code frequently emit `Repo.query!`,
`Ecto.Adapters.SQL.query!`, or `fragment(...)` calls where user input
is concatenated (`<>`) or string-interpolated (`#{...}`) directly into
the SQL string. Ecto provides parameterised placeholders (`$1` / the
second list arg of `Repo.query`) and the `fragment("col = ?", value)`
form precisely to avoid this; the `Ecto.Query.API.fragment/1` docs
explicitly warn that interpolating into the SQL string disables
parameter binding.

## What it flags

A line in a `.ex` / `.exs` file that calls one of:

- `Repo.query` / `Repo.query!`
- `Ecto.Adapters.SQL.query` / `query!` / `query_many` / `query_many!`
- `fragment(`

…with a tainted first SQL argument:

1. `"... #{x} ..."` interpolation, OR
2. concatenation with `<>`, OR
3. a bare variable identifier (no quoted literal at all).

For `Ecto.Adapters.SQL.query` the second positional argument (the SQL
string) is examined since the first is the repo module.

## What it does NOT flag

- `Repo.query!("SELECT 1")` — pure literal.
- `Repo.query!("SELECT * FROM t WHERE id = $1", [id])` — parameterised.
- `fragment("col = ?", value)` — placeholder form.
- Lines suffixed with `# sql-ok`.
- Sinks inside `#` comments or string literals.

## Usage

```bash
python3 detect.py path/to/lib
```

Exit 1 on findings, 0 otherwise. Pure python3 stdlib.

## Worked example

```bash
./verify.sh
```

Should print `PASS` with `bad findings: >=5` and `good findings: 0`.

## Suppression

Append `# sql-ok` to the offending line if the SQL is operator-built
and reviewed.
