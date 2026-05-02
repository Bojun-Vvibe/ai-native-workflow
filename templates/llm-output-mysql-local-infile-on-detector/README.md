# llm-output-mysql-local-infile-on-detector

Static lint that flags MySQL/MariaDB configurations shipping with
`local_infile = 1` (or equivalent), enabling the
`LOAD DATA LOCAL INFILE` capability server-side.

When `local_infile` is enabled, a malicious or compromised MySQL
*server* can ask any connecting client to upload an arbitrary file
from the client's filesystem (the protocol allows the server to
request a file when the client has opted in). Combined with a
SQL-injection bug in any application using `LOAD DATA LOCAL INFILE`
— or with phishing a DBA into connecting to a hostile host — this
turns into arbitrary file read on the client, including
`/etc/passwd`, application secrets, or SSH keys.

Modern MySQL (8.0+) ships with `local_infile = OFF` by default. LLM
output frequently re-enables it, often pasted from old MySQL 5.x
tutorials:

```ini
[mysqld]
local_infile = 1
```

```dockerfile
CMD ["mysqld", "--local-infile=1"]
```

This detector flags those shapes while accepting:

- `local_infile = OFF` / `0` / `false` / `no`
- files containing `# mysql-local-infile-allowed` for committed dev
  fixtures or intentional bulk-load hosts
- comment lines (`#` prefix)

## What it catches

- `my.cnf` / `mysqld.cnf`: `local_infile = ON|1|true|yes` (and the
  `local-infile` hyphen variant) at any scope.
- Dockerfile `RUN` lines that `sed` / `echo` `local_infile` to a
  truthy value into a `my.cnf` file.
- `mysqld --local-infile` / `--local-infile=1` flags in Dockerfile
  `CMD` / `ENTRYPOINT` (bare flag is also flagged because it
  defaults to enabled).

## CWE references

- [CWE-22](https://cwe.mitre.org/data/definitions/22.html):
  Improper Limitation of a Pathname to a Restricted Directory
- [CWE-200](https://cwe.mitre.org/data/definitions/200.html):
  Exposure of Sensitive Information to an Unauthorized Actor
- [CWE-732](https://cwe.mitre.org/data/definitions/732.html):
  Incorrect Permission Assignment for Critical Resource

## False-positive surface

- `local_infile = OFF` (and `0` / `false` / `no`) is treated as safe.
- Any file containing the comment `# mysql-local-infile-allowed` is
  skipped wholesale (use this for legitimate bulk-load hosts).
- Lines starting with `#` are treated as comments and ignored.

## Worked example

```sh
$ ./verify.sh
bad=4/4 good=0/4
PASS

$ python3 detector.py examples/bad/my.cnf examples/bad/Dockerfile
examples/bad/my.cnf:3:local_infile = 1 enables LOAD DATA LOCAL INFILE (client-side file disclosure risk)
examples/bad/Dockerfile:2:Dockerfile echo sets local_infile = 1" in my.cnf
examples/bad/Dockerfile:3:mysqld --local-infile=1" enables LOAD DATA LOCAL INFILE
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
