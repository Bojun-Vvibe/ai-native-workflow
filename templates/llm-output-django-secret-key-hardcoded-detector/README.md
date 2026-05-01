# llm-output-django-secret-key-hardcoded-detector

Static lint that flags Django `settings.py`-style files where
`SECRET_KEY` is assigned a hardcoded string literal instead of being
loaded from the environment, a secrets manager, or a key-derivation
step.

A hardcoded `SECRET_KEY` is a high-impact footgun: it signs session
cookies, password-reset tokens, `signing.dumps` payloads, CSRF tokens
(older Django), and `messages`-framework cookies. If it lands in a
repo, anyone with read access can forge any of those.

LLMs asked to "give me a Django settings.py" routinely produce:

```python
SECRET_KEY = "django-insecure-9!*8z@kq..."
SECRET_KEY = 'changeme'
SECRET_KEY = "abc123"
```

This detector flags those shapes in any `*.py` file (Django settings
files are not always literally named `settings.py`).

## What it catches

- `SECRET_KEY = "<literal>"` / `SECRET_KEY = '<literal>'`
- `SECRET_KEY: str = "<literal>"` (PEP-526 annotated assignment)
- f-strings with no interpolation: `SECRET_KEY = f"abc"`
- Concatenated string literals: `SECRET_KEY = "abc" + "def"`
- Dict-literal forms: `"SECRET_KEY": "abc"` inside a config dict.

## What it does NOT flag

- `SECRET_KEY = os.environ["X"]` / `os.environ.get("X")`
- `SECRET_KEY = os.getenv("X", default)` (default treated as fallback)
- `SECRET_KEY = config("X")` / `env("X")` (`python-decouple`,
  `django-environ`, etc.)
- `SECRET_KEY = SECRETS["X"]` / `vault.get("...")` / any subscription
  or attribute access on the right-hand side.
- Lines tagged with a trailing `# secret-key-ok` comment (test
  fixtures, ephemeral CI keys).
- Files containing `# secret-key-ok-file` at the top.

## CWE references

- [CWE-798](https://cwe.mitre.org/data/definitions/798.html):
  Use of Hard-coded Credentials
- [CWE-321](https://cwe.mitre.org/data/definitions/321.html):
  Use of Hard-coded Cryptographic Key
- [CWE-547](https://cwe.mitre.org/data/definitions/547.html):
  Use of Hard-coded, Security-relevant Constants

## False-positive surface

- Test fixtures intentionally pinned to a known constant. Suppress
  per-line with `# secret-key-ok` or per-file with
  `# secret-key-ok-file`.
- Indirected loads (`SECRET_KEY = SECRETS["KEY"]`) are not flagged
  because the literal lives outside the source tree.
- Django's own dev placeholder `django-insecure-...` IS flagged on
  purpose; the prefix exists precisely to be searched for.

## Worked example

```sh
$ ./verify.sh
bad=5/5 good=4/4
PASS
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=clean/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
