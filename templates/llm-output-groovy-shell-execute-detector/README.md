# llm-output-groovy-shell-execute-detector

Static detector for Groovy source where LLM-generated code spawns an
OS process from a String that includes user-controllable input,
producing command / argv injection.

## What it flags

| Sink                                      | Why                                          |
| ----------------------------------------- | -------------------------------------------- |
| `"...${x}".execute()`                     | GDK `String#execute` tokenises on whitespace |
| `Runtime.getRuntime().exec(cmdString)`    | Same tokeniser; shell metachars unfiltered   |
| `new ProcessBuilder(cmdString).start()`   | Single-String ctor, same tokeniser           |
| `["sh","-c", x].execute()`                | Explicit shell wrapper -- canonical antipattern |

The detector requires the argument to either contain GString
interpolation (`${...}` / `"$x"`), `+` concatenation, or to mention a
known-tainted token (`params`, `request`, `args`, `env`,
`System.getenv`, `binding`, `input`, `userInput`).

## What it does NOT flag

* `"ls -la".execute()` -- pure literal.
* `Runtime.getRuntime().exec(["git", "log", branch] as String[])`
  -- array form, no shell tokenisation hazard.
* `new ProcessBuilder(["git", "log", branch]).start()` -- list form.
* `// "rm -rf ${x}".execute()` -- single-line comment.

## Usage

```bash
python3 detect.py path/to/src/
python3 detect.py build.gradle
```

Exit codes:

* `0` -- no findings
* `1` -- at least one finding
* `2` -- usage error

Output format: `path:line: label: snippet`.

## Verify

```bash
./verify.sh
```

Asserts every `examples/bad/*` triggers a finding and every
`examples/good/*` is silent.

## Design notes

Regex-based, stdlib-only, no Groovy parser dependency. Designed to run
as a tight CI gate against LLM-emitted Groovy / Gradle diffs. The
"tainted on the same line" fallback is intentional: LLMs frequently
build the command string one line above and call `.execute()` on a
local. We accept some false positives in exchange for catching that
common shape; the verify suite documents the boundary.
