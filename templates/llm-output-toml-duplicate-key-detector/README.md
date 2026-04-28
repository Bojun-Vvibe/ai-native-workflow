# llm-output-toml-duplicate-key-detector

Pure-stdlib, code-fence-aware detector that catches **duplicate keys
at the same table scope** inside TOML blocks an LLM emits in markdown.

TOML 1.0.0 says duplicate keys MUST be an error, and every real
parser enforces that. But the LLM that emitted the doc has no parser
in the loop — it happily produces:

```toml
[server]
port = 8080
port = 8081
```

The bug surfaces when the doc is finally fed to a parser, often in
production CI: `toml: duplicate key "port"`. This detector flags it
at emit time so the model can be re-prompted before the doc ships.

## What it flags

| kind | meaning |
|---|---|
| `duplicate_key` | the same bare/quoted key appears twice inside the same active table or inline-table scope |

## Scope rules

- `[a.b]` opens a new active table; keys defined under it do not
  collide with keys under `[a.c]` or `[a]`.
- `[[arr]]` opens a new array-of-tables element; each `[[arr]]` gets
  its own scope (so two elements may both define `url`).
- A `#` comment is stripped before parsing, with quote-awareness so
  `note = "k = v"` is left alone.

Out of scope by design: full TOML grammar, multi-line strings,
implicit-table conflicts, mixing dotted-key + table-header for the
same path. A grammar checker is somebody else's template.

## Usage

```sh
python3 detect.py examples/bad.md
python3 detect.py examples/good.md
```

Findings go to stdout, one per line:

```
block=<N> line=<L> kind=duplicate_key key=<k> first_line=<L0>
```

Summary `total_findings=<N> blocks_checked=<M>` is printed to stderr.
Exit code is `1` if any findings, `0` otherwise — wire it into a
pre-publish or pre-commit gate.

Only fenced blocks tagged `toml`, `conf`, `config`, or `ini`
(case-insensitive) are inspected. `ini` is included because LLMs
often mislabel TOML as ini.

## Worked example — bad input

`examples/bad.md` contains three TOML blocks, two of which have
duplicate keys.

```
$ python3 detect.py examples/bad.md
block=1 line=3 kind=duplicate_key key=name first_line=2
block=1 line=9 kind=duplicate_key key=port first_line=8
block=2 line=3 kind=duplicate_key key=url first_line=2
# stderr: total_findings=3 blocks_checked=2
# exit:   1
```

Read across the findings: `name` is duplicated inside `[package]`,
`port` is duplicated inside `[server]`, and a separate inline TOML
block redefines `url` inside `[database]`.

## Worked example — good input

`examples/good.md` exercises the negative cases that must NOT fire:

- Same key (`name`) in two different tables — different scopes.
- Same key (`url`) in two `[[mirror]]` array-of-tables elements —
  each element is its own scope.
- A `#`-commented `port = 9999` line — must be ignored.
- A string value containing `key = value` — must not be parsed as
  an assignment.

```
$ python3 detect.py examples/good.md
# stderr: total_findings=0 blocks_checked=3
# exit:   0
```

## Composition

- Run alongside `llm-output-json-duplicate-key-detector` — same
  failure mode in a different format.
- Pair with a YAML duplicate-key detector (separate template) for
  the third leg of the config-format triangle.
- A grammar/lint detector (e.g. via `tomli` in the consuming
  pipeline) catches things this one deliberately skips.

## Files

- `detect.py` — checker.
- `examples/bad.md` — markdown with three TOML blocks; two have
  duplicate keys.
- `examples/good.md` — markdown with three TOML blocks, all clean.
- `README.md` — this file.

Stdlib only. Tested on Python 3.9+.
