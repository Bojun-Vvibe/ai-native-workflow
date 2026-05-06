# llm-output-netdata-web-bind-public-no-auth-detector

Stdlib-only **bash** detector that flags Netdata `netdata.conf`
files whose `[web]` section exposes the embedded HTTP API on a
public-facing socket without any authentication gate — that is,
binds to `*`, `0.0.0.0`, `::`, or a non-loopback IP **and** has
`allow connections from = *` (or omits the directive, which
defaults open) **and** does not enable
`bearer token protection = yes`.

Maps to **CWE-306** (Missing Authentication for Critical
Function), **CWE-200** (Exposure of Sensitive Information),
**CWE-1188** (Insecure Default Initialization), OWASP
**A05:2021 Security Misconfiguration**, **A01:2021 Broken Access
Control**.

## Why this is a problem

The Netdata agent ships a built-in HTTP API on TCP/19999 that
streams **per-second** metrics for everything the host knows about:
- every running process (name, command line, pid, RSS/CPU)
- every container (name, image, networking)
- every block device, network interface, IRQ, and cgroup
- every TCP connection (`netdata.conf` `[plugin:proc:/proc/net/tcp]`)
- systemd unit health, journald digest, sensors, IPMI, smartd, …

A reachable Netdata API without auth gives an attacker a perfect
pre-attack reconnaissance feed: which database is running, what
SSH keys are loaded into agents, when the operator is logged in,
what the host's external IP looks like from the inside,
which processes spike under load, and so on. It is the equivalent
of a permanently-open `top`, `ss -tnp`, `iotop`, and
`docker stats` for any internet-reachable scanner.

Netdata's own hardening guide is explicit: bind to localhost and
front it with a reverse proxy that adds auth, **or** turn on the
built-in `bearer token protection = yes`.

## Why LLMs ship this

The vendored `netdata.conf.sample`, the README in the official
helm chart, and most "monitor my homelab in 5 minutes" blog posts
ship `bind socket to IP = *` and never mention bearer tokens.
Models trained on that corpus produce the same shape: bind to all
interfaces, leave the ACL at default, never set the token.

## What this detector does

Scans a single file or recursively scans a directory for files
named `netdata.conf`, `netdata.conf.*`, or `*.netdata.conf`.

For each matched file it walks INI sections and, inside `[web]`,
extracts:

- `bind socket to IP = ...` (default: `*`)
- `allow connections from = ...` (default: `*` — open)
- `bearer token protection = yes|no` (default: `no`)
- `mode = none` short-circuits the check (web server disabled)

A finding is emitted when **all three** of the following hold:

1. the bind list contains a public token (`*`, `0.0.0.0`, `::`,
   `[::]`, or any non-loopback IPv4/IPv6 literal),
2. `allow connections from` is open (`*`, `all`, `0.0.0.0/0`,
   `::/0`, contains `*`, or is unset → defaults to `*`),
3. `bearer token protection` is not `yes`/`on`/`true`/`1`.

Comment lines (`#` and `;`) and blank lines are ignored; section
names are matched case-insensitively.

## Usage

```
./detect.sh <netdata.conf-or-dir>
```

## Exit codes

| Code | Meaning                                                       |
|------|---------------------------------------------------------------|
| 0    | PASS — no public-bind-without-auth observed                   |
| 1    | FAIL — at least one public-bind-without-auth observed         |
| 2    | usage error (missing arg or path does not exist)              |

## Validation

```
$ for f in fixtures/bad/*;  do ./detect.sh "$f" >/dev/null || echo "BAD detected: $f"; done
$ for f in fixtures/good/*; do ./detect.sh "$f" >/dev/null && echo "GOOD passed:  $f"; done
```

Result on the bundled fixtures: **bad=4/4 detected, good=0/4 false
positives, PASS**. Full command output is recorded in `RUN.md`.

## Limitations

- Treats any non-loopback IPv4/IPv6 literal as "public", including
  RFC1918 ranges. A bind to `10.0.0.5` with no auth gate **is**
  still a finding here on purpose: the agent is listening with no
  auth; whether the LAN it is on is "trusted" is a perimeter
  question outside this detector's scope.
- Does not follow `include` directives or `[web].web files
  override = ...` style overlays; point the detector at the final
  rendered config.
- Does not check whether a reverse proxy in front (nginx /
  traefik / caddy) adds auth — only the Netdata-side gate. Pair
  with a reverse-proxy-auth detector for full coverage.
- Does not parse the `[web]` `respect do not track` or
  `allow management from` sub-ACLs; a deployment that opens
  management endpoints to the world while keeping read API on
  loopback will not fire here.
