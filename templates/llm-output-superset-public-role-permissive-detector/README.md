# llm-output-superset-public-role-permissive-detector

Detect Apache Superset configurations that LLMs commonly emit which
hand the built-in `Public` role the same permissions as a logged-in
role (typically `Gamma` or `Admin`). When `PUBLIC_ROLE_LIKE` is set to
the name of a real role in `superset_config.py`, every anonymous
visitor of the Superset UI / SQL Lab / charts API inherits that
role's permissions on the next `superset init` run. The Superset
security docs (`security.html#public`) call this out: the `Public`
role exists for one purpose — exposing dashboards anonymously — and
binding it to `Gamma` (let alone `Admin`) silently turns the entire
deployment into an unauthenticated data warehouse front-end.

The hardening knobs that close this off are:

- Leave `PUBLIC_ROLE_LIKE` unset (the default; the `Public` role gets
  no permissions and anonymous visitors see only the login screen).
- Set `PUBLIC_ROLE_LIKE = None` explicitly for the same effect.
- Set `AUTH_ROLE_PUBLIC = "Public"` (the default) and keep the
  `Public` role's permission list empty in the Flask-AppBuilder UI.

When asked "share a Superset dashboard publicly" or "let anonymous
users see this chart", LLMs routinely paste either
`PUBLIC_ROLE_LIKE = "Gamma"` (which exposes every database
connection, every saved query, and SQL Lab itself), or
`PUBLIC_ROLE_LIKE_GAMMA = True` (the legacy boolean knob that did
the same thing in pre-1.0 Superset and is still honored).

This detector is orthogonal to the
`llm-output-superset-secret-key-default-detector` (that one targets a
crypto material default; this one targets an authorization default)
and to the broader Flask-AppBuilder anonymous-role family — it is
specific to Superset's `superset_config.py` Python config dialect,
which is a different file format from every other detector in this
repo.

Related weaknesses: CWE-732 (Incorrect Permission Assignment for
Critical Resource), CWE-285 (Improper Authorization), CWE-269
(Improper Privilege Management).

## What bad LLM output looks like

Direct assignment to a logged-in role:

```python
PUBLIC_ROLE_LIKE = "Gamma"
```

Legacy boolean knob (still honored):

```python
PUBLIC_ROLE_LIKE_GAMMA = True
```

Promoting `Public` to admin (catastrophic, but LLMs do emit this when
asked "let anyone manage dashboards"):

```python
PUBLIC_ROLE_LIKE = "Admin"
```

Environment-driven assignment that resolves to a non-empty role:

```python
import os
PUBLIC_ROLE_LIKE = os.environ.get("SUPERSET_PUBLIC_ROLE", "Gamma")
```

## What good LLM output looks like

- `PUBLIC_ROLE_LIKE` is absent from the file entirely.
- `PUBLIC_ROLE_LIKE = None`.
- `PUBLIC_ROLE_LIKE = ""` (empty string; treated as "no binding" by
  Superset's `init` command).
- `PUBLIC_ROLE_LIKE_GAMMA = False`.

## Run the smoke test

```sh
bash detect.sh samples/bad/* samples/good/*
```

Expected output:

```
BAD  samples/bad/superset_config_admin.py
BAD  samples/bad/superset_config_env_default_gamma.py
BAD  samples/bad/superset_config_gamma.py
BAD  samples/bad/superset_config_legacy_gamma_true.py
GOOD samples/good/superset_config_default_role_only.py
GOOD samples/good/superset_config_legacy_gamma_false.py
GOOD samples/good/superset_config_none.py
GOOD samples/good/superset_config_unset.py
bad=4/4 good=0/4 PASS
```

Exit status is `0` only when every bad sample is flagged and zero
good samples are flagged.

## Detector rules

A file is flagged iff at least one of the following is true after
`#`-comment stripping:

1. **`PUBLIC_ROLE_LIKE` assigned to a non-empty string literal** whose
   value is not `None`. Both single- and double-quoted forms match.
2. **`PUBLIC_ROLE_LIKE` assigned via `os.environ.get(...)` (or
   `os.getenv(...)`) where the second argument** — the default — is a
   non-empty string literal. The environment may or may not be set at
   runtime; the LLM-emitted default is what an out-of-the-box
   `superset init` will apply.
3. **`PUBLIC_ROLE_LIKE_GAMMA = True`** (the legacy boolean knob).

`#` line comments and inline `# ...` tails are stripped before
matching. Whitespace around `=` is normalized. The detector does not
attempt to evaluate arbitrary Python — it pattern-matches the three
LLM-frequent shapes above.

## Known false-positive notes

- `PUBLIC_ROLE_LIKE = ""` is treated as good; Superset's
  `init_role` walks an empty string as "no source role" and assigns
  no permissions.
- A commented-out `# PUBLIC_ROLE_LIKE = "Gamma"` is treated as good;
  the comment stripper removes the entire line before matching.
- An assignment whose RHS is a function call other than
  `os.environ.get` / `os.getenv` (e.g.,
  `PUBLIC_ROLE_LIKE = pick_role()`) is treated as good-by-deferral;
  the detector cannot statically resolve the call. Pair this detector
  with whatever review process you use for non-literal config values.
- A file that imports `superset_config` from another module is not
  flagged on the import line; only assignments inside the file under
  inspection are checked.
