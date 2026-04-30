# llm-output-python-os-system-user-input-detector

Pure-stdlib python3 single-pass scanner that flags **`os.system` /
`os.popen` calls built from interpolated input** in `*.py` files.
This is the canonical Python command-injection footgun: both
functions hand their entire string argument to `/bin/sh -c`, so
any caller-controlled substring becomes shell-syntax-active.

## What it catches

Four interpolation shapes, on any of these vulnerable functions:

- `os.system`, `os.popen`, `os.popen2`, `os.popen3`, `os.popen4`
- legacy `commands.getoutput`, `commands.getstatusoutput`
- legacy `popen2.popen2/3/4`

Interpolation forms detected:

- f-string  — `os.system(f"ping -c 1 {host}")`
- `+` concat — `os.system("tar czf /tmp/x.tgz " + path)`
- `%` fmt   — `os.system("id %s" % user)`
- `.format` — `os.popen("ls {}".format(d))`

Finding kinds:

- `os-system-fstring`
- `os-system-concat`
- `os-system-percent`
- `os-system-format`

## What it does NOT catch (intentionally)

- `os.system("uptime")` — plain literal, no interpolation. A
  separate detector covers static-command best-practice; this
  one narrows to the security-critical interpolation signal so
  it stays high-precision.
- `subprocess.run([...])` and other argv-list shapes — those
  are the safe replacement.
- Lines marked with a trailing `# os-system-ok` comment.
- Occurrences inside `#` comments and string literals (so prose
  describing the bad pattern in a docstring will not fire).

## Files

- `detect.py` — single-file python3 stdlib scanner (no deps).
- `examples/bad/` — six `.py` files exercising all four
  interpolation shapes across `os.system`, `os.popen`, and the
  legacy `commands.getoutput` surface.
- `examples/good/` — four `.py` files showing safe shapes
  (argv-list `subprocess.run`, plain literal, prose-only mention,
  audited-and-suppressed test fixture).
- `verify.sh` — runs the detector against `bad/` and `good/`
  and asserts the expected counts and exit codes.

## Run

```bash
bash verify.sh
```

Expected: `PASS`, with at least 6 findings against `bad/` and 0
against `good/`.

## Safe replacement patterns

```python
# The only safe shape — argv list, no shell.
import subprocess

def ping(host: str) -> int:
    return subprocess.run(
        ["ping", "-c", "1", "--", host],
        check=False,
        timeout=5,
    ).returncode
```

If a fixture truly needs shell semantics on a fully
agent-controlled string, pin the path and audit the line:

```python
os.system("rm -f " + FIXTURE)  # os-system-ok — test-controlled
```

## Why LLMs emit the bad shape

`os.system(f"...")` is the shortest possible "run a command with
a variable in it" snippet in Python — fewer imports, fewer
characters, and decades of tutorial/blog corpus reinforcing it
as the default answer. The argv-list `subprocess.run([...])`
shape requires the caller to think about argument splitting,
which costs tokens and rarely shows up at the top of search
results. So token economy + corpus inertia together push the
unsafe shape into LLM completions.
