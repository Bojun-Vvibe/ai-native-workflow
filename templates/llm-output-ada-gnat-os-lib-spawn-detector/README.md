# llm-output-ada-gnat-os-lib-spawn-detector

Single-pass detector for **Ada `GNAT.OS_Lib.Spawn`-family** process-launch
sinks. Whenever the program name or argument list is built from user input
rather than a vetted constant, this is a classic command-injection sink.

## Why this exists

GNAT (the GNU Ada compiler) ships an `OS_Lib` package whose `Spawn` family
executes external programs. `System.OS_Lib` mirrors it in the runtime.
LLM-emitted Ada code reaches for `GNAT.OS_Lib.Spawn` whenever the model
needs "run a command" and almost never reasons about the trust boundary
on the program name or argument list.

```ada
GNAT.OS_Lib.Spawn (Program_Name, Args, Success);
Pid := GNAT.OS_Lib.Non_Blocking_Spawn (Cmd, Args);
GNAT.OS_Lib.Spawn_With_Filter (Cmd, Args, "filter.sh", OK);
```

Each of these passes attacker-controllable text to a child process.

## What it flags

| Construct                                 | Why                                |
| ----------------------------------------- | ---------------------------------- |
| `GNAT.OS_Lib.Spawn (...)`                 | Blocking spawn                     |
| `GNAT.OS_Lib.Non_Blocking_Spawn (...)`    | Async spawn                        |
| `GNAT.OS_Lib.Spawn_With_Filter (...)`     | Filtered variant                   |
| `System.OS_Lib.Spawn (...)`               | Runtime mirror, same surface       |
| `OS_Lib.Spawn (...)` (after `use ...`)    | `use`-shortened form               |
| Multi-line `GNAT.OS_Lib.Spawn\n  (...)`   | Whitespace / newline tolerated     |

## What it ignores

- A bare `Spawn (...)` after `use GNAT.OS_Lib;` — too noisy without
  the qualifier and too easy to false-positive on user-defined `Spawn`
  procedures. The detector requires the `OS_Lib` prefix.
- `Ada.Directories.*` — file ops, not spawn.
- Mentions of `GNAT.OS_Lib.Spawn (...)` inside `--` line comments or
  `"..."` string literals (with `""` escaped quotes handled).
- Lines marked with the suppression comment `-- spawn-ok`.

## Usage

```sh
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code `1` on any finding, `0` otherwise. Python 3 stdlib only,
no third-party dependencies. Recurses into directories looking for
`*.adb`, `*.ads`, `*.ada`.

## Verified output

Run against the bundled examples:

```
$ python3 detect.py examples/bad.adb
examples/bad.adb:14:4: ada-os-lib-spawn — GNAT.OS_Lib.Spawn ("/bin/sh", Args.all, Success);
examples/bad.adb:17:11: ada-os-lib-spawn — Pid := GNAT.OS_Lib.Non_Blocking_Spawn ("rm", Args.all);
examples/bad.adb:20:4: ada-os-lib-spawn — GNAT.OS_Lib.Spawn_With_Filter ("curl", Args.all, "filter.sh", Success);
examples/bad.adb:23:4: ada-os-lib-spawn — System.OS_Lib.Spawn ("bash", Args.all, Success);
examples/bad.adb:26:4: ada-os-lib-spawn-use — OS_Lib.Spawn ("python3", Args.all, Success);
examples/bad.adb:29:4: ada-os-lib-spawn — GNAT.OS_Lib.Spawn
# 6 finding(s)

$ python3 detect.py examples/good.adb
# 0 finding(s)
```

The `good.adb` file deliberately includes:

- a `"..."` literal containing the substring `GNAT.OS_Lib.Spawn (...)`
  as prose,
- `--` line comments mentioning `GNAT.OS_Lib.Spawn (` and the
  `OS_Lib.Spawn (` shortcut,
- normal `Ada.Directories.Create_Directory` (file op, not spawn),
- a variable named `Spawn_Result` (no qualifier, no parens, ignored),
- one suppressed `GNAT.OS_Lib.Spawn` call carrying the `-- spawn-ok`
  marker on the same line.

All are correctly *not* flagged.

## Design notes

- **Single pass per file**, two compiled regexes (case-insensitive
  because Ada identifiers are case-insensitive), plus an Ada source
  masker that blanks `--` line comments and `"..."` string contents
  while preserving column positions and newlines.
- The masker handles Ada's `""` doubled-quote escape inside strings.
- `re.DOTALL` is set so multi-line `GNAT.OS_Lib.Spawn\n  (...)` forms
  still match the qualifier-then-paren pattern.
- The use-shortened matcher (`OS_Lib.Spawn (...)`) skips any hit
  preceded by `.` to avoid double-counting fully-qualified calls.
- Suppression marker `-- spawn-ok` lets you whitelist a single line
  when the spawn is intentional and the program path + arguments
  have been audited.

## Layout

```
detect.py            # the scanner
examples/bad.adb     # six intentional violations
examples/good.adb    # zero violations, including a suppressed line
```
