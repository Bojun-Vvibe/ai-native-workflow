# llm-output-requests-verify-false-detector

Defensive lint pattern. Scans Python source for the
`requests.<method>(..., verify=False)` call shape and for
`urllib3.disable_warnings()`, both of which together silently turn off TLS
certificate verification.

This template exists because LLM-generated Python frequently reaches for
`verify=False` to "make the request work" against self-signed test servers,
and the change tends to survive into production code review unless a CI
linter catches it.

## What it flags

- `requests.get|post|put|delete|patch|head|options|request(..., verify=False)`
- `urllib3.disable_warnings(...)` (any args)

## What it does not flag

- Session-style calls like `s.get(..., verify=False)` — too easy to attribute
  the wrong way without type info; keep the rule conservative.
- `verify=<expr>` where the expression is anything other than the literal
  `False` (e.g. a CA bundle path or a variable).

## Layout

```
detector.py        # python3 stdlib only, AST based
bad/               # files the detector MUST flag
good/              # files the detector MUST NOT flag
```

## Run it

```
python3 detector.py bad/    # expect 3 findings, exit code 3
python3 detector.py good/   # expect 0 findings, exit code 0
```

## Verification (worked example)

```
$ python3 detector.py bad/ ; echo "exit=$?"
bad/sample_disable_warnings.py:4:urllib3.disable_warnings() suppresses TLS warnings
bad/sample_get.py:4:requests call with verify=False
bad/sample_post.py:5:requests call with verify=False
exit=3

$ python3 detector.py good/ ; echo "exit=$?"
exit=0
```

bad=3, good=0 — PASS.

## Wiring into CI

Drop `detector.py` into your repo (e.g. `tools/lint/`) and call it from a
pre-commit hook or a CI step that points at the directories that hold
LLM-generated code. Non-zero exit means the gate fails.
