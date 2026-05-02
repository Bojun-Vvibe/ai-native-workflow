# llm-output-redis-bind-0000-detector

Static lint that flags Redis `redis.conf` files where `bind` is set to
`0.0.0.0` (or `::`, `*`) — i.e. listening on every network interface —
without an authentication mechanism in front of it (no `requirepass`,
and `protected-mode no`).

Redis ships with `bind 127.0.0.1 -::1` and `protected-mode yes` so a
fresh install only listens on loopback. LLM-generated configs routinely
"fix the can't-connect-from-app-server" problem by setting
`bind 0.0.0.0` and turning protected-mode off, accidentally publishing
an unauthenticated Redis to the network. This is one of the most
heavily exploited misconfigurations on the public internet (open Redis
→ `CONFIG SET dir` → write SSH keys / cron entries → RCE).

## What it catches

- `bind 0.0.0.0`, `bind ::`, `bind *` (bare or among other addresses).
- Same shape with extra leading whitespace and `bind` followed by
  multiple addresses.
- Combined with `protected-mode no` → flagged with an extra "no
  protection" finding.
- `requirepass foobared` (the historic placeholder) is treated as
  unset.

## CWE references

- [CWE-668](https://cwe.mitre.org/data/definitions/668.html): Exposure
  of Resource to Wrong Sphere
- [CWE-306](https://cwe.mitre.org/data/definitions/306.html): Missing
  Authentication for Critical Function
- [CWE-1188](https://cwe.mitre.org/data/definitions/1188.html):
  Initialization of a Resource with an Insecure Default

## False-positive surface

- Containerized Redis on a private overlay network where the host is
  genuinely isolated. Suppress per file with a comment
  `# redis-bind-all-allowed` anywhere in the file.
- `bind 127.0.0.1` / `bind ::1` / specific non-wildcard IPs are
  treated as safe.
- `requirepass <non-empty, non-default>` downgrades the bind-all
  finding to info-only (no exit code impact) unless `protected-mode
  no` is also present.

## Worked example

```sh
$ ./verify.sh
bad=4/4 good=0/4
PASS
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
