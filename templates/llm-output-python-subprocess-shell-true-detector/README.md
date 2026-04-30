# llm-output-python-subprocess-shell-true-detector

Pure-stdlib python3 line scanner that flags ``shell=True`` (and
``os.system`` / ``os.popen`` / legacy ``commands.getoutput``) usage in
LLM-emitted Python code where the command argument is interpolated
from a non-literal source.

## Why

When ``subprocess.run(..., shell=True)`` is given a command string
built from a variable, f-string, ``%`` / ``.format`` expression, or
concatenation, every shell metacharacter in the interpolated value is
interpreted by ``/bin/sh``. A user input of ``"; rm -rf ~"`` becomes
a command separator, not a literal. This is OS command injection.

LLMs reach for ``shell=True`` by reflex because it lets them emit a
single string ("ls -la /tmp") instead of reasoning about argv
tokenisation, and because pipes / redirection (``|``, ``>``) only
work via the shell.

CWE references:

- **CWE-78**: OS Command Injection.
- **CWE-77**: Improper Neutralization of Special Elements used in a Command.
- **CWE-88**: Argument Injection.

## Usage

```sh
python3 detect.py path/to/runner.py
python3 detect.py path/to/project/   # recurses *.py
```

Exit code 1 if any unsafe usage found, 0 otherwise.

## What it flags

- ``subprocess.<run|Popen|call|check_call|check_output>(<expr>, shell=True, ...)``
  where ``<expr>`` is not a bare string literal — i.e. it is a
  variable name, f-string, ``%`` / ``.format`` expression, or string
  concatenation.
- ``os.system(<expr>)`` where ``<expr>`` is not a bare string literal.
- ``os.popen(<expr>)`` with the same condition.
- ``commands.getoutput(<expr>)`` / ``commands.getstatusoutput(<expr>)``
  (Python 2 holdover that LLMs still emit).

## What it does NOT flag

- ``subprocess.run(["ls", "-la", path])`` — argv form, no shell.
- ``subprocess.run("ls -la", shell=True)`` — fully literal command,
  no interpolation.
- ``os.system("date")`` — fully literal.
- Lines suffixed with ``# shell-true-ok`` (e.g. tightly controlled
  command construction with ``shlex.quote`` on every interpolated arg,
  audited).

## Verify the worked example

```sh
bash verify.sh
```

Asserts the detector flags every ``examples/bad/*.py`` case and is
silent on every ``examples/good/*.py`` case.
