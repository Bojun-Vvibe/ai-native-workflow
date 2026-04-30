# llm-output-eval-exec-detector

Defensive AST-based lint scanner. Catches the canonical remote-code-execution
pattern that LLM-generated Python ships when asked for a "calculator API",
"plugin loader", "dynamic config", or "remote handler":

```python
eval(user_supplied_string)        # arbitrary code execution
exec(payload.decode())            # arbitrary code execution
compile(src, "<plugin>", "exec")  # same, with extra steps
eval(f"{name} = {value}")         # f-string fed to eval is the same bug
```

The detector flags `eval` / `exec` / `compile` whenever the first argument is
**not** a string literal — i.e. any dynamic value (`Name`, `JoinedStr`,
`BinOp`, `Call`, `Subscript`, …). It also recognises `builtins.eval` and
`__builtins__.eval` access patterns.

## What it flags

- `eval(x)` / `exec(x)` / `compile(x, ...)` with any non-literal first arg
- `builtins.eval(x)` / `__builtins__.exec(x)`
- `eval(f"...")` (f-string) / `eval("a" + b)` (concat) / `eval(some_var)`
- `eval()` / `exec()` with zero args (almost always a bug in flight)

## What it does not flag

- `eval("1 + 2")` — constant string literal first arg. Still discouraged, but
  not the dynamic-RCE pattern this rule targets. Pair with a separate "no
  eval at all" rule if you want a stricter policy.
- `ast.literal_eval(...)` — the safe replacement. Explicitly allowed.

## Layout

```
detector.py        # python3 stdlib only, AST based
bad/               # files the detector MUST flag
good/              # files the detector MUST NOT flag
verify.sh          # runs both halves, exits 0 only if both pass
```

## Run it

```
python3 detector.py bad/    # expect findings, non-zero exit
python3 detector.py good/   # expect 0 findings, exit code 0
bash verify.sh              # one-shot: passes only if both halves pass
```

## Verification (worked example)

```
$ bash verify.sh
=== detector vs bad/ (expect findings, non-zero exit) ===
bad/calc_service.py:7:eval() called with non-literal argument (Name)
bad/calc_service.py:12:eval() called with non-literal argument (JoinedStr)
bad/plugin_loader.py:8:exec() called with non-literal argument (Name)
bad/plugin_loader.py:13:exec() called with non-literal argument (Name)
bad/plugin_loader.py:17:compile() called with non-literal argument (Name)
bad/plugin_loader.py:18:exec() called with non-literal argument (Name)
exit=2

=== detector vs good/ (expect 0 findings, exit 0) ===
exit=0

PASS: bad=6 findings (exit 2), good=0 findings (exit 0)
```

## Wiring into CI

Drop `detector.py` into `tools/lint/` and call it from a pre-commit hook
pointed at your application source tree. Non-zero exit fails the gate.
