# llm-output-postgres-trust-auth-detector

Static lint that flags PostgreSQL `pg_hba.conf` files which grant
access via the `trust` authentication method on a non-loopback line.

`trust` means *no password, no certificate, no Kerberos — anyone who
can reach the TCP port wins*. It is appropriate only for Unix-socket
`local` lines on a single-tenant developer machine. LLMs asked to
"give me a pg_hba.conf that lets my app connect" routinely paste in:

```conf
host    all  all  0.0.0.0/0   trust
host    all  all  ::/0        trust
host    all  all  10.0.0.0/8  trust
```

…all of which expose the database to anyone who can route packets to
it.

## What it catches

Per non-comment, non-blank line with at least 4 fields, where:

- Connection type is `host`, `hostssl`, `hostnossl`, `hostgssenc`, or
  `hostnogssenc` (i.e. TCP, not Unix socket);
- Auth method (last token, ignoring trailing `key=value` options) is
  `trust`;
- Address is *not* loopback-only (`127.0.0.1/32`, `::1/128`, `localhost`,
  `samehost`).

`/0` CIDRs are called out as a separate, louder finding because they
are always public-internet patterns.

## What it does NOT flag

- `local all all trust` — Unix-socket local. (Promoted to a finding
  only if the file contains `# pg-trust-strict`.)
- `host all all 127.0.0.1/32 trust` and `::1/128 trust` — loopback.
- `host all all 0.0.0.0/0 scram-sha-256` — real auth method.
- `host all all 10.0.0.0/8 cert` — certificate auth.
- Lines suppressed with a trailing `# pg-trust-ok` comment.
- Files containing `# pg-trust-ok-file` anywhere.

## CWE references

- [CWE-287](https://cwe.mitre.org/data/definitions/287.html):
  Improper Authentication
- [CWE-306](https://cwe.mitre.org/data/definitions/306.html):
  Missing Authentication for Critical Function
- [CWE-668](https://cwe.mitre.org/data/definitions/668.html):
  Exposure of Resource to Wrong Sphere

## False-positive surface

- Single-tenant dev boxes that intentionally use `local ... trust`
  for the operator's UNIX user. Not flagged unless
  `# pg-trust-strict` is set.
- Throwaway compose-network `pg_hba.conf` files in CI fixtures.
  Suppress with `# pg-trust-ok-file`.
- Address fields with explicit netmask in the next column
  (e.g. `host all all 10.0.0.0 255.0.0.0 trust`) are normalized to
  `10.0.0.0/255.0.0.0` for reporting; loopback detection still works.

## Worked example

```sh
$ ./verify.sh
bad=5/5 good=0/4
PASS
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=Y_clean/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
