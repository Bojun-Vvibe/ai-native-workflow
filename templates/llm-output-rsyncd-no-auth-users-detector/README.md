# llm-output-rsyncd-no-auth-users-detector

Static lint that flags `rsyncd.conf` module definitions exposed
without an `auth users` line.

`rsyncd` modules without `auth users` are reachable by any client
that can speak rsync to the daemon TCP port (typically 873).
Combined with `read only = false` this is an unauthenticated remote
file-write primitive (CWE-306 / CWE-284); even with the default
`read only = true` it remains a bulk data exfiltration channel
(CWE-200).

LLM-generated `rsyncd.conf` files, container entrypoints, and
Ansible templates routinely emit:

```ini
[backup]
path = /srv/backup
read only = false
# no auth users, no secrets file
```

```ini
[public]
path = /var/www/public
hosts allow = *
```

This detector parses each `[module]` block and flags any module that
has a `path = ...` line but no non-empty `auth users = ...`.

## What it catches

- `[module]` blocks with `path = ...` and no `auth users`.
- `[module]` blocks with `auth users =` (empty value).
- Modules with `read only = false` are escalated in the message
  ("writable").
- Modules with a `secrets file` line but no `auth users` (the
  secrets file is unreachable without `auth users`, so this is
  almost certainly an LLM mistake).

## CWE references

- [CWE-306](https://cwe.mitre.org/data/definitions/306.html):
  Missing Authentication for Critical Function
- [CWE-284](https://cwe.mitre.org/data/definitions/284.html):
  Improper Access Control
- [CWE-200](https://cwe.mitre.org/data/definitions/200.html):
  Exposure of Sensitive Information to an Unauthorized Actor

## False-positive surface

- Files containing `# rsyncd-no-auth-allowed` are skipped wholesale
  (use for committed public-mirror fixtures).
- Modules with no `path =` line are treated as incomplete stubs and
  ignored.
- The global pre-`[module]` section is not flagged on its own;
  rsyncd does not propagate global `auth users` into modules, so
  each module is checked independently.

## Worked example

```sh
$ ./verify.sh
bad=4/4 good=0/3
PASS
```

## Files

- `detector.py` — scanner. Exit code = number of files with at
  least one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `run.sh` — thin wrapper that execs `verify.sh`.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
