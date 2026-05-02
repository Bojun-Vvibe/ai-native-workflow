# llm-output-postgres-listen-addresses-star-detector

Static lint that flags PostgreSQL `postgresql.conf` files that set
`listen_addresses = '*'` (or any non-loopback bind) while `pg_hba.conf`
is missing — or, when `pg_hba.conf` is provided, while it permits
`host ... 0.0.0.0/0 trust` or `host ... 0.0.0.0/0 password` style
entries.

LLM-generated PostgreSQL configs routinely paste:

```conf
listen_addresses = '*'
port = 5432
```

…with a `pg_hba.conf` containing:

```
host    all    all    0.0.0.0/0    trust
```

That combination publishes a passwordless SQL endpoint on every
interface — a category of exposure repeatedly observed in mass
ransomware campaigns against `postgres` Docker images.

## What it catches

- `listen_addresses` set to `'*'`, `'0.0.0.0'`, or any explicit
  non-loopback address.
- Companion `pg_hba.conf` (any file matching `pg_hba*.conf` in the same
  directory or passed alongside) containing `trust` auth on a
  non-loopback CIDR.
- Companion `pg_hba.conf` containing `password` (cleartext-on-the-wire,
  pre-MD5/SCRAM) on a non-loopback CIDR.
- The trifecta (exposed bind + non-loopback CIDR + `trust`) emits an
  extra summary finding.

## What is treated as safe

- `listen_addresses = 'localhost'` or `'127.0.0.1'` or `'::1'`.
- `listen_addresses` commented out (Postgres default is `localhost`).
- `pg_hba.conf` entries that use `scram-sha-256`, `md5`, `cert`,
  `gss`, `sspi`, `peer`, or `ident` on the non-loopback CIDR.
- `host ... samenet ...` and `host ... samehost ...` rows.
- Any file containing the suppression marker `# pg-public-allowed`.

## CWE references

- [CWE-306](https://cwe.mitre.org/data/definitions/306.html): Missing
  Authentication for Critical Function
- [CWE-284](https://cwe.mitre.org/data/definitions/284.html): Improper
  Access Control
- [CWE-319](https://cwe.mitre.org/data/definitions/319.html): Cleartext
  Transmission of Sensitive Information (for `password` auth)

## False-positive surface

- Local-dev compose files behind a private docker network. Suppress
  per file with `# pg-public-allowed`.
- Cloud-managed Postgres (RDS, Cloud SQL) where the IaC layer enforces
  network isolation independently of `postgresql.conf`. Suppress.
- Internal-only clusters that genuinely expect `listen_addresses='*'`
  but pin auth to `scram-sha-256` — these will pass clean already.

## Verified

`verify.sh` prints `good=<flagged>/<total>`, so a clean good column is
`0/N`.

```
$ ./verify.sh
bad=4/4 good=0/4
PASS
```

Per-file output (sample):

```
examples/bad/01-listen-star.postgresql.conf:4:listen_addresses exposes non-loopback ('*')
examples/bad/02-listen-zero.postgresql.conf:2:listen_addresses exposes non-loopback ('0.0.0.0')
examples/bad/03-listen-mixed.postgresql.conf:2:listen_addresses exposes non-loopback ('localhost,10.0.0.5')
examples/bad/04-pg_hba-trust-world.pg_hba.conf:3:pg_hba host row uses weak auth 'trust' on non-loopback address '0.0.0.0/0'
examples/bad/04-pg_hba-trust-world.pg_hba.conf:4:pg_hba host row uses weak auth 'trust' on non-loopback address '::/0'
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding (capped at 255).
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=Y/Z` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
