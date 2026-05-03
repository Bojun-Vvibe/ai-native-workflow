# llm-output-grafana-anonymous-admin-role-detector

Static lint that flags Grafana INI configurations
(`grafana.ini`, `custom.ini`, `defaults.ini`) where the
`[auth.anonymous]` section has `enabled = true` together with
`org_role` set to `Admin` or `Editor`.

Grafana's anonymous-auth mode lets unauthenticated visitors act as
a real user inside an organization. With `org_role = Viewer` (the
shipped default), that's only read access to dashboards. With
`org_role = Editor` or `org_role = Admin`, an unauthenticated
visitor on the network can mutate dashboards, install plugins,
add data sources, exfiltrate query results from any backing
database, and — for `Admin` — manage org users and API keys
(CWE-862, CWE-732).

LLM-generated `grafana.ini` files routinely emit:

```ini
[auth.anonymous]
enabled = true
org_role = Admin
```

or:

```ini
[auth.anonymous]
enabled  = true
org_name = Main Org.
org_role = Editor
```

This detector parses each INI section and flags
`[auth.anonymous]` sections where `enabled` is truthy AND
`org_role` is `Admin` or `Editor` (case-insensitive).

## What it catches

- `enabled = true` (or `True`, `1`, `yes`, `on`) with
  `org_role = Admin` / `Editor` in `[auth.anonymous]`.
- The same combination expressed across line-continuations or
  with surrounding whitespace.
- Equivalent forms with quoted values (`org_role = "Admin"`).

## CWE references

- [CWE-862](https://cwe.mitre.org/data/definitions/862.html):
  Missing Authorization
- [CWE-732](https://cwe.mitre.org/data/definitions/732.html):
  Incorrect Permission Assignment for Critical Resource
- [CWE-284](https://cwe.mitre.org/data/definitions/284.html):
  Improper Access Control

## False-positive surface

- Files containing `# grafana-anon-admin-allowed` are skipped
  wholesale (use for committed kiosk-mode fixtures behind an
  auth proxy).
- `org_role = Viewer` is accepted — that's the documented
  read-only kiosk pattern.
- `enabled = false` is accepted regardless of `org_role`.
- Sections other than `[auth.anonymous]` are not inspected.

## Worked example

```sh
$ ./verify.sh
bad=4/4 good=0/3
PASS
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `run.sh` — thin wrapper that execs `verify.sh`.
- `smoke.sh` — alias for `run.sh`, kept for harness symmetry.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
