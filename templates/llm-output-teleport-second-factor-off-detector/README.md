# llm-output-teleport-second-factor-off-detector

Static lint that flags Teleport YAML configs which disable second-
factor authentication on the `auth_service`. Catches both the
explicit `second_factor: off` LLMs emit when asked to "fix the login
loop" and the subtler `second_factor: optional` shape which still
permits factor-less password-only logins.

## Why this matters

Teleport brokers SSH, kubectl, database, desktop, and application
access into your fleet. Its `auth_service.authentication.second_factor`
key controls whether users — including locally-defined `editor` /
`access` accounts and any SSO-mapped accounts — must present a second
factor. The values that **disable** real 2FA are:

- `off` / `false` / `no` — single-factor (password only).
- `optional` — clients may register zero factors and still log in
  with password only. The "optional" naming makes this look benign
  in code review; it is not.

Acceptable values are `on`, `otp`, `webauthn`, and the
`hardware_key` / `hardware_key_touch` family.

The reason this ends up in committed `teleport.yaml` so often: the
docs' troubleshooting page mentions `second_factor: off` as a recovery
option when an admin is locked out. LLMs cheerfully reproduce that as
the "fix" and operators paste it into prod.

## What it catches

The file must contain a top-level `auth_service:` key. Then:

1. `auth_service.authentication.second_factor` set to any of
   `off` / `false` / `no` / `0` / `disable` / `disabled`.
2. `auth_service.authentication.second_factor` set to `optional`.

Indentation is tracked manually (stdlib only — no PyYAML dependency)
so the directive must live under `authentication:` which itself lives
under `auth_service:`. A `second_factor: off` line buried in some
unrelated file (e.g. a Traefik config) will not trigger.

## What it accepts as safe

- `second_factor: on` / `otp` / `webauthn` / `hardware_key` /
  `hardware_key_touch`.
- Files that don't contain a top-level `auth_service:` key.
- Files annotated `# teleport-2fa-off-allowed` (air-gapped lab nets).

## CWE references

- [CWE-308](https://cwe.mitre.org/data/definitions/308.html): Use of
  Single-factor Authentication.
- [CWE-287](https://cwe.mitre.org/data/definitions/287.html): Improper
  Authentication.
- [CWE-1390](https://cwe.mitre.org/data/definitions/1390.html): Weak
  Authentication.

## Worked example

```sh
$ ./verify.sh
bad=4/4 good=0/4
PASS
```

Per-finding output for one bad sample:

```sh
$ python3 detector.py examples/bad/02-optional.yaml
examples/bad/02-optional.yaml:10:auth_service.authentication.second_factor is "optional" — clients may register zero factors and authenticate with password only
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  prints `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag (4 fixtures).
- `examples/good/` — expected to pass clean (4 fixtures).
