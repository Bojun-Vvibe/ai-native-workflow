# llm-output-kotlin-runtime-exec-string-concat-detector

Static detector for Kotlin source emitted by an LLM that builds an OS command
via string concatenation / interpolation and hands it to `Runtime.exec(...)` or
`ProcessBuilder(...)`. This pattern is the textbook **CWE-78 OS Command
Injection** sink: any unsanitised value (HTTP param, env, user input) flows
straight into a shell-parsed argv.

## Why this matters for LLM output

LLMs love to "help" by writing one-liners like:

```kotlin
Runtime.getRuntime().exec("ping -c 1 " + host)
```

That looks fine in a prompt-and-demo, but when `host` is attacker-controlled
the argv is split by the JVM (`StringTokenizer`) and any embedded shell
metacharacter or extra token is executed as a separate argument or — worse —
when wrapped in `sh -c` becomes a full injection. The safe form always passes
an **array** of literal arguments, never a concatenated string, and never
mixes interpolation into the first array element.

## Sinks flagged

| ID                              | Pattern                                                 |
| ------------------------------- | ------------------------------------------------------- |
| `runtime-exec-string-interp`    | `Runtime.getRuntime().exec("..." + x)` / `"...$x..."`   |
| `runtime-exec-array-interp`     | `Runtime.getRuntime().exec(arrayOf("...$x..."))`        |
| `process-builder-string-interp` | `ProcessBuilder("..." + x)` / interpolated single-arg   |
| `process-builder-list-interp`   | `ProcessBuilder(listOf("...$x...", ...))`               |
| `process-builder-command-set`   | `.command("...$x...")` chained call                     |

Pure literal strings (no `+`, no `$`, no `${}`) are ignored.

## Usage

```sh
python3 detect.py path/to/kotlin/sources
```

- Exit `0` and no output: clean.
- Exit `1` and one line per finding (`file:line:rule: snippet`) on stderr+stdout.

## Run the worked example

```sh
./verify.sh
```

`examples/bad/` contains 8 vulnerable forms; `examples/good/` contains 4 safe
forms (literal-only argv, hard-coded `listOf` of literals, `ProcessBuilder`
constructed from a sanitised allow-list, etc.).

## Pitfalls / known limitations

- **Regex-based**, not a full Kotlin parser. Comments containing `Runtime.exec`
  with a `+` will false-positive; suppress with `// detector:ignore` on the
  same line if needed.
- Does **not** chase taint across functions. A helper `fun cmd(x: String) =
  "ping " + x` followed by `Runtime.getRuntime().exec(cmd(host))` is missed.
  Catching that requires a real call-graph; this detector is the cheap first
  filter on raw LLM output.
- Multi-line concatenation (string broken across lines with `+` at line end)
  is only partially detected — the trailing `+` line will trip the rule, but
  exotic formatters can hide it. Run a code formatter first if precision
  matters.
- Kotlin string templates inside `"""triple-quoted"""` blocks are flagged the
  same as regular strings. That's intentional — the sink is the same.
