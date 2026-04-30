# llm-output-django-debug-true-detector

Defensive lint pattern. Scans Python source (typically `settings.py` or
`settings_*.py`) for the three classic unsafe defaults that LLM-generated
Django projects tend to ship:

- `DEBUG = True`
- `ALLOWED_HOSTS` containing the wildcard `"*"`
- `SECRET_KEY` set to an obvious placeholder literal (short, empty, or a
  known marker like `changeme` / `django-insecure-…`)

LLM scaffolding for Django often copies the `django-admin startproject`
defaults verbatim into files named `settings_prod.py` or `settings_live.py`.
A CI lint step that scans for these three lines catches the regression early.

## What it flags

- `DEBUG = True` (literal `True`, not env-driven)
- `ALLOWED_HOSTS = [..., "*", ...]` or tuple form
- `SECRET_KEY = "<short or placeholder>"` literal

## What it does not flag

- Env-driven assignments (`DEBUG = os.environ.get("DJANGO_DEBUG") == "1"`)
- Real-looking long random `SECRET_KEY` literals (still discouraged, but not
  this rule's job — pair with a separate "secret in source" scanner)

## Layout

```
detector.py        # python3 stdlib only, AST based
bad/               # files the detector MUST flag
good/              # files the detector MUST NOT flag
```

## Run it

```
python3 detector.py bad/    # expect findings, non-zero exit
python3 detector.py good/   # expect 0 findings, exit code 0
```

## Verification (worked example)

```
$ python3 detector.py bad/ ; echo "exit=$?"
bad/settings_debug.py:2:DEBUG = True in settings module
bad/settings_debug.py:3:ALLOWED_HOSTS contains wildcard '*'
bad/settings_debug.py:4:SECRET_KEY looks like a placeholder literal
bad/settings_prod.py:2:DEBUG = True in settings module
bad/settings_prod.py:3:ALLOWED_HOSTS contains wildcard '*'
bad/settings_prod.py:4:SECRET_KEY looks like a placeholder literal
exit=2

$ python3 detector.py good/ ; echo "exit=$?"
exit=0
```

bad=2 files flagged, good=0 — PASS.

## Wiring into CI

Drop `detector.py` into your repo (e.g. `tools/lint/`) and call it from a
pre-commit hook that points at the directories that hold settings files.
Non-zero exit means the gate fails.
