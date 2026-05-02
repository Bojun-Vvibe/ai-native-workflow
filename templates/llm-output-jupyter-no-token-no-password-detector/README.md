# llm-output-jupyter-no-token-no-password-detector

Static lint that flags Jupyter Notebook / JupyterLab / Jupyter Server
configuration files (or equivalent shell / Docker / CLI fragments)
that disable both token and password authentication, leaving the
notebook server fully open:

- Python config (`jupyter_notebook_config.py`, `jupyter_server_config.py`):
  `c.NotebookApp.token = ''`, `c.ServerApp.token = ''`,
  `c.NotebookApp.password = ''`, `c.ServerApp.password = ''`,
  `c.NotebookApp.disable_check_xsrf = True`.
- JSON config: `{"NotebookApp": {"token": "", "password": ""}}` /
  `{"ServerApp": {...}}`.
- CLI fragments: `jupyter notebook --NotebookApp.token=''
  --NotebookApp.password=''`, `jupyter lab --ServerApp.token=''`,
  or the combined `--no-browser --ip=0.0.0.0 --allow-root` style
  invocations with empty token *and* empty password.

## Why this matters

Jupyter ships with a randomly generated token specifically because a
notebook server gives the caller a remote Python REPL — i.e., remote
code execution as the kernel user. The single most common LLM answer
to "I keep getting prompted for a token" is to set `token = ''` and
`password = ''`, which turns the kernel into an unauthenticated RCE
endpoint. Combined with the equally common `ip = '0.0.0.0'`, this is
how Jupyter servers end up in mass-scanner indexes.

This detector is **orthogonal** to bind-address detectors: it fires
on the missing-credential misconfig regardless of whether the
notebook is also listening on every interface, because an
unauthenticated kernel is dangerous even on a "trusted" LAN
(co-tenant containers, sidecars, lateral movement).

## CWE references

- [CWE-306](https://cwe.mitre.org/data/definitions/306.html): Missing
  Authentication for Critical Function
- [CWE-287](https://cwe.mitre.org/data/definitions/287.html): Improper
  Authentication
- [CWE-1188](https://cwe.mitre.org/data/definitions/1188.html):
  Initialization of a Resource with an Insecure Default

## What it accepts

- Any non-empty token literal (`c.ServerApp.token = 'abc123'`).
- Any non-empty hashed password literal
  (`c.ServerApp.password = 'argon2:...'`, `'sha1:...'`).
- Configurations that read the token from an env var
  (`os.environ['JUPYTER_TOKEN']`, `os.getenv(...)`) — the detector
  cannot prove the env value is non-empty, but the pattern is the
  documented secure default.
- `# jupyter-open-allowed` opt-out marker anywhere in the file.

## False-positive surface

- README prose mentioning `token = ''` in a docstring or comment is
  not flagged (the assignment must be at line-start, modulo
  indentation, and not inside a `#` comment).
- A file that sets only `token = ''` but also sets a non-empty
  `password = '...'` is **not** flagged — Jupyter accepts either.
- A file that sets only `password = ''` but also sets a non-empty
  `token = '...'` is **not** flagged.

## Worked example

```sh
$ ./verify.sh
bad=6/6 good=0/5
PASS
```

Per-finding output:

```sh
$ python3 detector.py examples/bad/01-py-token-and-password-empty.py
examples/bad/01-py-token-and-password-empty.py:3:c.ServerApp.token set to empty string and no password configured — kernel is unauthenticated RCE
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
