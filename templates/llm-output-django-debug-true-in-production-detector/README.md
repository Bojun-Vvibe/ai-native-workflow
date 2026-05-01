# llm-output-django-debug-true-in-production-detector

Static lint that flags Django settings modules shipping
`DEBUG = True` (and friends) to production.

## Why LLMs emit this

`django-admin startproject` generates a `settings.py` whose top
half reads:

```python
DEBUG = True
ALLOWED_HOSTS = []
```

Every Django tutorial, every Stack Overflow answer, and every
"hello world" repo carries that same pair. When a developer asks
an LLM "write me a Django settings file" or "fix my `DisallowedHost`
error", the model's shortest path to a working app is to keep
`DEBUG = True` and set `ALLOWED_HOSTS = ['*']`. Both are
catastrophic in production:

- `DEBUG = True` renders the yellow Django error page on any
  unhandled exception. That page leaks the full traceback, local
  variables, request headers, environment variables, installed
  apps, and SQL fragments — including hardcoded API keys and DB
  passwords if they live in `settings.py`.
- `ALLOWED_HOSTS = ['*']` removes the host-header check, so the
  debug page is reachable from any internet client that can resolve
  the IP, not just from the canonical hostname.

## What it catches

Per file, line-level findings:

- `DEBUG = True` / `DEBUG=True` / `DEBUG : bool = True` /
  `DEBUG = 1`
- `TEMPLATE_DEBUG = True` (legacy Django <1.8 toggle, still in
  training data)
- `ALLOWED_HOSTS = ['*']` / `ALLOWED_HOSTS = ["*"]` /
  `ALLOWED_HOSTS = ('*',)`

Per file, whole-file finding:

- A production-named settings file (`settings_prod*.py`,
  `production.py`, `prod.py`, anything under a path containing
  `production`) that hardcodes `DEBUG = True` AND never reads any
  env var (no `os.environ`, `os.getenv`, `env(`, `config(`)

## What it does NOT flag

- `DEBUG = False`
- `DEBUG = os.environ.get('DJANGO_DEBUG') == '1'`
- `DEBUG = config('DEBUG', default=False, cast=bool)` (django-environ)
- `ALLOWED_HOSTS = ['example.com', 'www.example.com']`
- Lines with a trailing `# dj-debug-ok` comment
- Files containing `dj-debug-ok-file` anywhere

## How to detect

```sh
python3 detector.py path/to/django-project/
```

Exit code = number of files with a finding (capped 255). Stdout:
`<file>:<line>:<reason>`.

## Safe pattern

```python
import os

DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"

ALLOWED_HOSTS = os.environ.get(
    "DJANGO_ALLOWED_HOSTS", "example.com"
).split(",")
```

Or with `django-environ`:

```python
import environ
env = environ.Env(DEBUG=(bool, False))
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["example.com"])
```

## Refs

- CWE-489: Active Debug Code
- CWE-209: Generation of Error Message Containing Sensitive
  Information
- OWASP Top 10 (2021) A05: Security Misconfiguration
- Django docs: "Deployment checklist" — `DEBUG` must be `False`
- Django docs: `ALLOWED_HOSTS` setting

## Verify

```sh
bash verify.sh
```

Should print `bad=4/4 good=0/3 PASS`.
