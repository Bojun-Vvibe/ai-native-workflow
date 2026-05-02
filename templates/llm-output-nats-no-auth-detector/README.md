# llm-output-nats-no-auth-detector

Static lint that flags NATS server config files (`nats-server.conf`,
`nats.conf`) which expose a non-loopback listener without any client
authorization configured.

## Why this matters

NATS happily accepts unauthenticated PUB/SUB on every subject when no
`authorization { ... }` block, no operator/resolver JWT mode, and no
mTLS-with-`verify: true` is configured. If the listener is bound to
`0.0.0.0` / `::` (or `host` is omitted, which defaults to all
interfaces), any host on the network can publish, subscribe, drain
queues, or hit `$SYS` admin requests when the system account is at
its default. This pattern shows up routinely in LLM-generated configs
because the canonical "hello world" snippet for NATS is just:

```hocon
port: 4222
http_port: 8222
```

…and learners paste that straight into prod.

## What it catches

- No `host` / `listen` directive (defaults to all interfaces) **and**
  no auth.
- Explicit non-loopback `host` / `listen` (e.g. `0.0.0.0`, `::`,
  public IP) **and** no auth.
- `authorization { ... }` block present but empty / placeholder
  (`token: "changeme"`, missing `password`, etc.).
- `tls { verify: false }` does not count as authentication.

## What it accepts as authentication

- `authorization { user, password }` with a non-placeholder password.
- `authorization { token }` with a non-placeholder token.
- `authorization { users = [...] }` (any non-empty list).
- `authorization { users = [{ nkey }] }` (NKey-based).
- Decentralized JWT mode: `operator: ...` + `resolver: ...` both set.
- `tls { verify: true }` (mTLS with client-cert required).

## CWE references

- [CWE-306](https://cwe.mitre.org/data/definitions/306.html): Missing
  Authentication for Critical Function
- [CWE-284](https://cwe.mitre.org/data/definitions/284.html): Improper
  Access Control
- [CWE-668](https://cwe.mitre.org/data/definitions/668.html): Exposure
  of Resource to Wrong Sphere

## False-positive surface

- Embedded test harnesses on private docker networks. Suppress per
  file with a comment `# nats-no-auth-allowed` anywhere in the file.
- `host: 127.0.0.1` / `host: ::1` / `host: localhost` only is treated
  as safe.
- Files that contain neither `port` nor `listen` are skipped (not a
  server config).

## Worked example

```sh
$ ./verify.sh
bad=5/5 good=0/5
PASS
```

Per-finding output (one bad sample):

```sh
$ python3 detector.py examples/bad/02-bind-all-no-authz.conf
examples/bad/02-bind-all-no-authz.conf:2:NATS listener binds non-loopback (0.0.0.0) without authorization / operator+resolver / mTLS verify
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
