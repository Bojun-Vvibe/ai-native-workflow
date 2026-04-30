# llm-output-subprocess-shell-true-detector

Single-pass python3 stdlib scanner for the canonical OS-command-injection
sink in LLM-emitted Python: `subprocess.*(..., shell=True)` (and the
related `os.system` / `os.popen` / legacy `commands.getoutput` shapes)
where the command argument is built from non-literal data.

## Why it exists

LLMs reflexively reach for `shell=True` whenever a prompt says "run this
command", because the shortest copy-paste recipe on the public internet
uses it. The result is a textbook injection sink: any value spliced into
the command string with f-strings, `%`, `.format()`, `+`, or a bare
variable reference goes through `/bin/sh -c` and an attacker who controls
that value can chain `;`, `|`, backticks, `$(...)`, or redirects.

The fix is almost always trivial — pass a list and drop `shell=True`:

```python
subprocess.run(["ls", user])           # safe
subprocess.run(f"ls {user}", shell=True)  # injection sink
```

This detector is conservative on purpose. It only flags `shell=True`
calls where the first argument *looks dynamic*. Pure literals like
`subprocess.run("uptime", shell=True)` are smelly but not injection
sinks, so they pass.

## What it flags

- `subprocess.run | Popen | call | check_call | check_output(...,
  shell=True)` where the first argument is an f-string, `%`-format,
  `.format(...)`, `+`-concatenation, a bare name/attribute, or otherwise
  not a single string literal.
- `os.system(<non-literal>)` — `os.system` is `shell=True` by
  definition, so any non-literal arg is an injection sink.
- `os.popen(<non-literal>)` — same shape.
- `commands.getoutput(<non-literal>)` and `commands.getstatusoutput(<non-literal>)`
  — legacy Python 2 API still produced by some LLMs.

## What it does NOT flag

- List-form calls: `subprocess.run(["ls", "-la"])`, `subprocess.Popen(["cat", path])`.
- `shell=False` (explicit or default).
- Pure string literals with `shell=True`: `subprocess.run("uptime", shell=True)`.
- `os.system("uptime")` with a literal.
- Lines with the trailing suppression marker `# shell-true-ok`.
- Occurrences inside `#` comments or string literals (the scanner masks
  both before matching, so the docstring above doesn't self-flag).

## Usage

```bash
python3 detect.py path/to/file_or_dir [more paths ...]
```

Exit code:

- `0` — no findings
- `1` — at least one finding
- `2` — usage error

Targets `*.py` files plus any file whose first line is a python shebang.

## Worked example

`examples/bad/` contains 8 dangerous shapes; `examples/good/` contains
8 safe shapes plus the suppression marker. `verify.sh` asserts
`bad >= 8` and `good == 0`.

```
$ ./verify.sh
bad findings:  8 (rc=1)
good findings: 0 (rc=0)
PASS
```

Verbatim scanner output on `examples/bad/`:

```
examples/bad/bad_cases.py:8:1: subprocess-run-shell-true-dynamic — subprocess.run(f"ls {user}", shell=True)
examples/bad/bad_cases.py:11:1: subprocess-Popen-shell-true-dynamic — subprocess.Popen("grep %s file.txt" % user, shell=True)
examples/bad/bad_cases.py:14:1: subprocess-call-shell-true-dynamic — subprocess.call("cat {}".format(user), shell=True)
examples/bad/bad_cases.py:17:1: subprocess-check_output-shell-true-dynamic — subprocess.check_output("echo " + user, shell=True)
examples/bad/bad_cases.py:21:1: subprocess-check_call-shell-true-dynamic — subprocess.check_call(cmd, shell=True)
examples/bad/bad_cases.py:24:1: os-system-dynamic — os.system(f"touch {user}.lock")
examples/bad/bad_cases.py:27:1: os-popen-dynamic — os.popen("which " + user)
examples/bad/bad_cases.py:31:1: commands-getoutput-dynamic — commands.getoutput("ps -ef | grep " + user)
# 8 finding(s)
```

## Suppression

Add `# shell-true-ok` at the end of any line you have audited.

## Layout

```
llm-output-subprocess-shell-true-detector/
├── README.md
├── detect.py
├── verify.sh
└── examples/
    ├── bad/bad_cases.py
    └── good/good_cases.py
```

## Limitations

- Single-line analysis. A `subprocess.run(` whose call spans many lines
  isn't reassembled — extend with a parenthesis-aware multi-line buffer
  if your codebase formats long calls.
- No taint tracking. The dynamic-vs-literal classifier is purely
  syntactic. A constant assembled at module load from a literal table
  will be treated as dynamic if it looks like a bare name. That's the
  right default for a pre-merge linter; a `# shell-true-ok` opt-out
  exists for the audited cases.
- No cross-file analysis.
