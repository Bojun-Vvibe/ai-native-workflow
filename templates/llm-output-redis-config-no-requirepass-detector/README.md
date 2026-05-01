# llm-output-redis-config-no-requirepass-detector

Static lint that flags Redis `redis.conf` files that ship without
authentication and/or with `protected-mode` disabled while bound to a
non-loopback interface.

A Redis instance with no `requirepass` (and no ACL `user` entries with
passwords), `protected-mode no`, and `bind 0.0.0.0` (or any
non-loopback bind, or no `bind` at all on Redis < 6.2) is a well-known
internet-wide compromise vector: attackers write SSH keys into
`~/.ssh/authorized_keys` via `CONFIG SET dir` + `SAVE`, load arbitrary
modules via `MODULE LOAD`, or simply exfiltrate the keyspace.

LLM-generated `redis.conf` files routinely paste in:

```conf
bind 0.0.0.0
protected-mode no
# requirepass commented out
```

This detector flags those config shapes.

## What it catches

- `protected-mode no` without `requirepass` and without an ACL `user`
  with a real password.
- `bind` on a non-loopback interface (or absent `bind`, which on Redis
  < 6.2 meant "all interfaces") without auth.
- Placeholder `requirepass` values (`foobared`, `changeme`, `password`,
  empty string) treated as missing.
- ACL `user ... on nopass` shapes treated as missing auth.
- The trifecta (bind exposed + protected-mode no + no auth) emits an
  extra summary finding.

## CWE references

- [CWE-306](https://cwe.mitre.org/data/definitions/306.html): Missing
  Authentication for Critical Function
- [CWE-284](https://cwe.mitre.org/data/definitions/284.html): Improper
  Access Control
- [CWE-668](https://cwe.mitre.org/data/definitions/668.html): Exposure
  of Resource to Wrong Sphere

## False-positive surface

- Local-dev compose files behind a private docker network. Suppress
  per file with a comment `# redis-no-auth-allowed` anywhere in the
  file.
- `bind 127.0.0.1 ::1` only is treated as safe.
- `port 0` (TCP disabled, Unix socket only) is treated as safe.
- `requirepass` values that are real (non-placeholder) secrets are
  accepted, including indirected `${REDIS_PASS}`-style strings.

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
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
