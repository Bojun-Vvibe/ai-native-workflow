# llm-output-mongodb-bind-ip-all-detector

Static lint that flags MongoDB `mongod.conf` files (or equivalent
shell / Docker / CLI fragments) which bind the daemon to every
interface, i.e.:

- YAML `net.bindIp: 0.0.0.0` (or `::`, `[::]`, lists containing them)
- YAML `net.bindIpAll: true`
- Legacy INI `bind_ip = 0.0.0.0`, `bind_ip_all = true`
- `mongod --bind_ip 0.0.0.0` / `mongod --bind_ip_all`

## Why this matters

MongoDB 3.6 changed the default to `bindIp: 127.0.0.1` precisely
because the previous "all interfaces" default was responsible for the
huge wave of unauthenticated MongoDB ransom sweeps in 2017. Reverting
to `0.0.0.0` because "I want it reachable from the other container" is
the single most common LLM-suggested fix for connectivity problems —
and it is wrong: the right fix is a private network plus auth, not a
wider listener.

This detector is **orthogonal** to "no auth" / "no TLS" detectors. It
fires on the listener-exposure misconfig regardless of whether
`security.authorization` is also turned off, because the exposure
itself is independently bad: it expands blast radius, gates safety on
layers that have historically been disabled accidentally, and removes
the primary defense-in-depth that 3.6 shipped on purpose.

## CWE references

- [CWE-668](https://cwe.mitre.org/data/definitions/668.html): Exposure
  of Resource to Wrong Sphere
- [CWE-200](https://cwe.mitre.org/data/definitions/200.html): Exposure
  of Sensitive Information to an Unauthorized Actor
- [CWE-1188](https://cwe.mitre.org/data/definitions/1188.html):
  Initialization of a Resource with an Insecure Default

## What it accepts

- `bindIp: 127.0.0.1` (or any list of loopback / non-`0.0.0.0`
  addresses).
- IPv6 loopback `::1`.
- Private-range bind addresses (`10.x`, `192.168.x`, etc.) — note
  that this detector does not validate that the address is actually
  private; it only refuses the explicit "all interfaces" sentinels.
- `# mongodb-bind-all-allowed` opt-out marker anywhere in the file.

## False-positive surface

- README prose that *mentions* `bindIp` in a comment without a real
  directive is not flagged (the line must match the YAML / INI / CLI
  shapes).
- CLI fragments are only checked on lines containing `mongod`, so
  `--bind_ip 0.0.0.0` inside an unrelated tool's docs is ignored.

## Worked example

```sh
$ ./verify.sh
bad=6/6 good=0/5
PASS
```

Per-finding output:

```sh
$ python3 detector.py examples/bad/01-bindip-zero.yaml
examples/bad/01-bindip-zero.yaml:4:net.bindIp includes all-interfaces address (0.0.0.0) — mongod will accept connections from every reachable network
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
