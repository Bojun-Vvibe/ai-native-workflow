# llm-output-markdown-table-leading-pipe-consistency-detector

A small python3 stdlib linter that flags GFM markdown tables in which some
rows begin with a leading `|` and others do not.

## What defect this catches

GitHub-flavored markdown tables let each row optionally start (and end) with
a pipe character. Both forms render correctly in isolation, but mixing them
inside a single table is a common LLM output defect — typically a sign that
the table was glued together from two differently formatted fragments. The
mix also breaks naive table parsers and diff tools.

This detector treats each contiguous table block separately. A block must
contain a GFM separator row (e.g. `| --- |` or `:---:`) to qualify. Any
single block that contains both leading-pipe rows and no-leading-pipe rows
is reported. Code fences are stripped before analysis.

## When to use

Run as a post-generation lint step on any markdown asset where tables matter
— specs, comparison docs, eval reports, status dashboards.

## Inputs / outputs

- **Input**: one markdown file path.
- **Output (stdout)**: per-table summary plus per-row locations.
- **Exit code**: `1` if any table mixes the two styles, `0` otherwise,
  `2` on bad usage.

## Usage

```
python3 detect.py path/to/file.md
echo "exit=$?"
```

## Worked example

The `worked-example/` subdir contains a deliberately inconsistent `bad.md`
with two tables — one clean, one mixed — and the expected detector output.
Verify with:

```
python3 detect.py worked-example/bad.md > /tmp/out.txt; echo "exit=$?"
diff worked-example/expected-output.txt /tmp/out.txt
```

`diff` should print nothing and the script should exit `1`.
