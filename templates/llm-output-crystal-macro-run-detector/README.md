# llm-output-crystal-macro-run-detector

Single-pass detector for **Crystal compile-time macro execution sinks**:
`{{ run(...) }}`, `{{ system(...) }}`, and backtick `` `...` `` commands
inside macro brackets `{{ ... }}` / `{% ... %}`. These primitives run
arbitrary programs at *compile time* and substitute their output into
the AST — full build-time RCE if the path or arguments are
attacker-controllable.

## Why this exists

Crystal macros run during compilation. The `run` macro method takes a
program path and arguments, executes it, and pastes its stdout back
into the source. LLM-emitted Crystal code reaches for `{{ run(...) }}`
whenever the model is unsure how to express compile-time codegen and
almost never reasons about the trust boundary on the path / arguments.

```crystal
CODEGEN = {{ run("./helpers/codegen", env("BUILD_TAG")) }}
HOST    = {{ system("uname -a") }}
TAG     = {{ `git rev-parse HEAD` }}
```

Each of these executes an external program at build time.

## What it flags

| Construct                            | Why                              |
| ------------------------------------ | -------------------------------- |
| `{{ run("...") }}`                   | Compile-time program execution   |
| `{{ run(path, *args) }}`             | Built arguments — true RCE sink  |
| `{{ system("...") }}`                | Macro shell-out                  |
| ``{% x = `cmd` %}``                  | Backtick command in macro block  |
| ``{{ `cmd` }}``                      | Backtick in macro interpolation  |
| Multi-line `{{\n  run(\n    ...) }}` | Whitespace tolerated             |

## What it ignores

- **Runtime** `Process.run`, `system`, backtick `` `cmd` `` *outside*
  of `{{ }}` / `{% %}` brackets. Those are normal shell-out covered
  by other detectors.
- `{{ ... }}` interpolations that don't include `run` / `system` /
  backticks (e.g. `{{ @type.name.stringify }}`).
- Mentions of `{{ run("evil") }}` inside `# line` comments or `"..."`
  string literals (string interpolation `#{...}` content is also
  masked since it is evaluated at runtime, not compile time).
- Lines marked with the suppression comment `# macro-run-ok`.

## Usage

```sh
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code `1` on any finding, `0` otherwise. Python 3 stdlib only,
no third-party dependencies. Recurses into directories looking for
`*.cr`.

## Verified output

Run against the bundled examples:

```
$ python3 detect.py examples/bad.cr
examples/bad.cr:7:16: crystal-macro-run — CODEGEN = {{ run("./helpers/codegen", "User") }}
examples/bad.cr:10:16: crystal-macro-run — CONFIG  = {{ run("./gen", env("BUILD_TAG")) }}
examples/bad.cr:13:13: crystal-macro-system — HOST = {{ system("uname -a") }}
examples/bad.cr:16:12: crystal-macro-backtick — TAG = {{ `git rev-parse HEAD` }}
examples/bad.cr:19:15: crystal-macro-backtick — {% commit = `git log -1 --format=%H` %}
examples/bad.cr:23:5: crystal-macro-run — run(
# 6 finding(s)

$ python3 detect.py examples/good.cr
# 0 finding(s)
```

The `good.cr` file deliberately includes:

- runtime `Process.run` and runtime backticks (outside macro brackets),
- a `"..."` literal containing the substring `{{ run("evil") }}` as prose,
- a `#` comment mentioning `{{ run("evil") }}` and `{% sys = \`cmd\` %}`,
- a benign macro interpolation `{{ @type.name.stringify }}`,
- a suppressed `{{ run("./helpers/audited") }}` with the
  `# macro-run-ok` marker.

All are correctly *not* flagged.

## Design notes

- **Single pass per file**, three compiled regexes, plus a Crystal
  source masker that blanks `#` line comments and `"..."` string
  contents while preserving column positions and newlines.
- The detector locates macro brackets `{{ ... }}` and `{% ... %}`
  on masked text, then searches *within each bracket* for `run(`,
  `system(`, and backtick commands. This avoids false positives on
  runtime calls and on prose that mentions macro syntax.
- Suppression marker `# macro-run-ok` lets you whitelist a single
  line when the macro execution is intentional and the program path
  + arguments have been audited.

## Layout

```
detect.py            # the scanner
examples/bad.cr      # six intentional violations
examples/good.cr     # zero violations, including a suppressed line
```
