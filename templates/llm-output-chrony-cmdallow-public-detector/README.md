# llm-output-chrony-cmdallow-public-detector

Detect chrony NTP daemon configurations that LLMs commonly emit
with the chronyc control socket effectively exposed to the public
network. chrony's `cmdallow` directive is an ACL that gates
chronyc commands (`makestep`, `burst`, `dump`, `sources`,
`tracking`, `settime`, …) when they arrive over the network. By
default the control socket binds to localhost only and refuses
remote commands. Two bad shapes appear over and over in
LLM-generated chrony configs:

1. The model writes `cmdallow all` (or the equivalent bare
   `cmdallow`, `cmdallow 0.0.0.0/0`, `cmdallow ::/0`) "to make
   chronyc work from another box". Without explicit `cmddeny all`
   afterwards, every reachable peer can drive the daemon.
2. The model scopes `cmdallow` to a real subnet (looks
   "tightened") but also writes `bindcmdaddress 0.0.0.0` so the
   socket is reachable from anywhere — the ACL only narrows which
   peers the daemon will *answer*, while the bind makes the
   socket itself visible to scanners on the public NIC.

## Bad patterns

1. `cmdallow all` (or bare `cmdallow`, or `cmdallow 0.0.0.0/0`,
   or `cmdallow ::/0`) without a later `cmddeny all`.
2. `cmdallow <real-subnet>` paired with `bindcmdaddress` set to a
   non-loopback address (`0.0.0.0`, `::`, an interface address,
   etc.).

## Good patterns

- No `cmdallow` and no `bindcmdaddress` at all (chrony's defaults
  refuse remote commands).
- Explicit loopback bind: `bindcmdaddress 127.0.0.1` /
  `bindcmdaddress ::1`.
- `cmdallow 127.0.0.0/8` or `cmdallow ::1` (loopback ACL).
- A wide-open `cmdallow` that is then clamped down by an explicit
  `cmddeny all` later in the file.

## Tests

```sh
./detect.sh samples/bad/* samples/good/*
```

Verified-runnable smoke output (verbatim):

```
BAD  samples/bad/01-cmdallow-all.conf
BAD  samples/bad/02-cmdallow-bare.conf
BAD  samples/bad/03-cmdallow-default-route.conf
BAD  samples/bad/04-cmdallow-subnet-public-bind.conf
GOOD samples/good/01-defaults.conf
GOOD samples/good/02-explicit-loopback-bind.conf
GOOD samples/good/03-cmdallow-loopback.conf
GOOD samples/good/04-cmdallow-all-but-cmddeny-all.conf
bad=4/4 good=0/4 PASS
```

## Why this matters

chrony's chronyc protocol is not authenticated by default — the
historical design assumed loopback-only access. When `cmdallow`
admits a remote peer, that peer can call `makestep` to slam the
system clock, `dump` to read the daemon's measurement state, or
exercise other commands that quietly degrade the host. NTP-daemon
clock manipulation is a known pivot for breaking certificate
validity windows, defeating Kerberos ticket lifetimes, and
confusing audit-log timestamps.

The detector deliberately:

- Treats bare `cmdallow` (no argument) the same as `cmdallow all`
  because chrony's parser does.
- Treats `cmdallow all` followed by `cmddeny all` as deliberate
  (chrony applies the most-specific match; an explicit `cmddeny
  all` is a clear operator intent to lock the socket back down).
- Does *not* fire on `bindcmdaddress 0.0.0.0` alone, because
  chrony still denies remote commands when no `cmdallow` line is
  present. We only flag combinations that actually grant remote
  access.
- Strips both `#` and `!` comments (chrony.conf accepts both)
  before matching, so commentary that mentions `cmdallow all` does
  not false-fire.

Bash 3.2+ / coreutils only. No network calls.
