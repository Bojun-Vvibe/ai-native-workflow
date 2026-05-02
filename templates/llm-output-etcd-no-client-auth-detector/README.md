# llm-output-etcd-no-client-auth-detector

## Purpose

Detects etcd configurations (CLI flags, systemd unit files, YAML config,
docker/compose snippets) that disable client authentication and/or expose the
client API on non-loopback interfaces without TLS client certs.

When an LLM emits etcd configuration as part of an infrastructure-as-code
suggestion, it commonly inherits the upstream "quickstart" defaults that bind
`--listen-client-urls=http://0.0.0.0:2379` with `--client-cert-auth=false`.
That posture exposes the entire key/value store (which typically holds
Kubernetes Secrets, lease state, and cluster membership) to anyone who can
reach the port.

## Signals (any one is sufficient to flag)

1. `--listen-client-urls` (or YAML key `listen-client-urls`) bound to
   `0.0.0.0`, `::`, or a non-loopback IP **and** the URL scheme is `http://`
   (i.e. plaintext).
2. `--client-cert-auth=false` (or YAML `client-cert-auth: false`) — explicit
   opt-out of client cert auth.
3. `--auth-token=` set to the literal `simple` while the listener is
   non-loopback (simple token auth is documented as not for production).
4. The flag `--client-cert-auth` is entirely absent from a config that also
   advertises a non-loopback client URL — etcd defaults to no client auth.

## How the detector works

`detector.sh` runs a sequence of `grep -E` passes over each input file. It
emits one line per finding in the form:

```
FLAG <signal-id> <file>:<lineno> <matched-text>
```

Exit code is `0` always (the smoke harness counts FLAG lines, not exit codes,
so a single detector invocation can report multiple findings per file without
short-circuiting).

The detector is purely lexical. It does NOT:
- connect to any etcd endpoint,
- attempt authentication,
- parse YAML semantically (we accept the FP cost in exchange for portability —
  no Python/yq dependency).

## False-positive risks

- A comment that quotes the bad pattern as an example of what NOT to do will
  be flagged. Mitigation: callers should review FLAG output, not auto-block.
- A config that listens on `0.0.0.0:2379` over HTTPS with peer-cert-only
  trust may be flagged by signal 1 if the scheme is mistakenly written
  `http://`; this is intentional — plaintext on a public bind is itself the
  bug.
- Local dev/test fixtures (CI ephemeral clusters) will trigger. Callers
  typically scope the detector to `prod/`, `infra/`, or `deploy/` paths.

## Fixtures

- `fixtures/bad/`: 4 snippets, each isolating one of the signals above.
- `fixtures/good/`: 3 snippets showing localhost-bind, full mTLS, and
  RBAC-enabled token auth on a TLS listener.

## Smoke

`bash smoke.sh` asserts `bad=4/4` flagged and `good=0/3` flagged. Any
deviation prints a DIFF block and exits non-zero.
