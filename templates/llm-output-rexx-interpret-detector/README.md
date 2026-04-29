# llm-output-rexx-interpret-detector

Single-pass python3-stdlib scanner that flags REXX dynamic-string-eval
sinks in LLM-emitted REXX (`*.rexx`, `*.rex`, `*.cmd` REXX-flavoured)
code.

## What it flags

REXX has one canonical "compile and run a string at runtime" sink, plus
a couple of close cousins that are equally dangerous when the string is
user-controlled:

* `INTERPRET expr` — the headline sink. Treats the value of `expr` as
  REXX source and runs it inline in the current variable scope.
* `CALL VALUE(...)` and `CALL (varName)` indirect-name forms — call
  whose target name is computed from a string at runtime.
* `SIGNAL VALUE(...)` and `SIGNAL (varName)` — non-local jump to a
  label whose name is computed from a string at runtime.
* `ADDRESS VALUE(...)` — switches the host environment string from a
  computed value (so the next `"..."` host command is dispatched to a
  shell name the model picked at runtime).
* The `RXFUNCADD` registration of `SysLoadFuncs`-style runtime function
  loaders is out of scope (that is dynamic *binding*, not dynamic
  *eval*).

## Why this matters

`INTERPRET` in classic / Open Object REXX is exactly Python's `exec(s)`
for the REXX VM: arbitrary REXX statements, full host-environment
dispatch, full filesystem access via `"address command ..."`. LLMs
reach for `INTERPRET` whenever a prompt asks for "dynamic dispatch"
or "configurable behaviour" — almost always the wrong tool, and in the
worst case a remote-code-execution sink when the interpreted string
came from input.

## What is masked before scanning

* `/* ... */` block comments (REXX standard).
* `--` line comments (Open Object REXX extension).
* `'...'` and `"..."` string literals.

REXX is case-insensitive; the regexes use `re.IGNORECASE`.

## Suppression

A trailing `/* interpret-ok */` or `-- interpret-ok` comment on the
same line suppresses every finding on that line. Use sparingly and
never on user-tainted input.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code `1` if any findings, `0` otherwise. Recurses into
directories looking for `*.rexx`, `*.rex`, `*.cmd`.

## Worked example

```
$ python3 detect.py examples/bad
examples/bad/01_interpret_user_input.rexx:5:1: interpret — interpret cmd
examples/bad/02_call_value_dispatch.rex:6:1: call-value — call value(handler) name
examples/bad/03_signal_value_jump.rexx:4:1: signal-value — signal value(target)
# 3 finding(s)

$ python3 detect.py examples/good
# 0 finding(s)
```
