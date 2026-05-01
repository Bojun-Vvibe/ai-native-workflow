# llm-output-rabbitmq-default-guest-credential-detector

Static lint that flags RabbitMQ configs and client code which rely on
the built-in `guest` / `guest` admin account in a way that is reachable
from the network.

## Background

RabbitMQ ships with a `guest` user that has full admin privileges.
Since RabbitMQ 3.3 this account is hard-restricted to loopback via
`loopback_users = guest` (classic config) or
`loopback_users.guest = true` (sysctl-style config). The upstream
[Access Control guide][rmq-access] explicitly calls this out as the
reason `guest` exists at all: it's a bootstrap admin you talk to from
`localhost`, then you create real users.

LLM-generated snippets routinely undo that protection because the
fastest way to make a "connection refused" error go away is to:

```ini
loopback_users = none           # classic
loopback_users.guest = false    # sysctl
```

…or to paste an `amqp://guest:guest@some.host:5672/` URI into a
service that runs on a different machine than the broker. Either move
hands an admin account to anyone who can route packets to port 5672.

[rmq-access]: https://www.rabbitmq.com/access-control.html

## What it catches

- Classic config: `loopback_users = []` / `loopback_users = none`.
- Sysctl config: `loopback_users.guest = false` (any of false/no/off/0).
- Erlang term: `{loopback_users, []}` inside `rabbitmq.config`.
- `amqp://guest:guest@HOST` / `amqps://guest:guest@HOST` URIs in any
  source file when `HOST` is not loopback.
- Client-code key/value pairs that set both `username = "guest"` and
  `password = "guest"` against a non-loopback `host` / `hostname` /
  `server` / `broker` setting (or no host setting, which is also
  flagged conservatively).

Loopback hosts are `127.0.0.0/8`, `::1`, and `localhost`. The detector
strips an optional port before matching.

## CWE references

- [CWE-521](https://cwe.mitre.org/data/definitions/521.html): Weak
  Password Requirements (a known default credential is the worst case
  of this).
- [CWE-798](https://cwe.mitre.org/data/definitions/798.html): Use of
  Hard-coded Credentials.
- [CWE-1392](https://cwe.mitre.org/data/definitions/1392.html): Use of
  Default Credentials.

## False-positive surface

- Local-laptop sandboxes that genuinely keep `guest` on a loopback
  bind. The default RabbitMQ config is treated as safe.
- CI test rigs on isolated networks. Suppress per file with a comment
  containing `rabbitmq-guest-allowed`.
- Client code that resolves credentials via env vars or a secret store
  is not flagged (we only flag literal `"guest"` for both fields).

## Worked example

```sh
$ ./verify.sh
bad=5/5 good=0/4
PASS
```

## Files

- `detector.py` — scanner. Exit code = number of findings emitted.
- `verify.sh` — runs every fixture in `examples/bad` and `examples/good`
  and reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — must trip the detector.
- `examples/good/` — must run clean.

## Verification

Output of `bash verify.sh` on this checkout:

```
bad=5/5 good=0/4
PASS
```
