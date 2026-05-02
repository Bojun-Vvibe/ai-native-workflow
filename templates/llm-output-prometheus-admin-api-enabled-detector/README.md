# llm-output-prometheus-admin-api-enabled-detector

## Purpose

Detects Prometheus server invocations or unit files that enable
`--web.enable-admin-api` (and/or `--web.enable-lifecycle`) without an external
auth proxy in front. The admin API exposes destructive endpoints — most
notably `POST /api/v1/admin/tsdb/delete_series`, `snapshot`, and
`clean_tombstones` — and the lifecycle API exposes `POST /-/reload` and
`POST /-/quit`. Both are unauthenticated by Prometheus itself.

When an LLM is asked to "make Prometheus reload config from CI" or "let me
delete bad series", it commonly proposes adding these flags to the server
command line. The fix is to keep them off, or to gate them behind an
authenticating reverse proxy bound to a private interface.

## Signals (any one is sufficient to flag)

1. `--web.enable-admin-api` (with or without `=true`) on the same line as
   the `prometheus` binary, in a systemd `ExecStart=`, in a docker/compose
   `command:` array, or in a Kubernetes container `args:` list.
2. `--web.enable-lifecycle` (or `=true`) — same surfaces.
3. `--web.listen-address` bound to `0.0.0.0:` or a non-loopback IP **and**
   either of signals 1/2 present in the same file.
4. A Helm-style `values.yaml` snippet with `enableAdminAPI: true` or
   `enableLifecycle: true` under a `prometheus`/`server`/`extraFlags`
   context (we approximate by matching the literal keys; FP risk noted
   below).

## How the detector works

`detector.sh` performs targeted `grep -nE` passes per signal and emits one
`FLAG <signal-id> <file>:<lineno> <text>` line per finding. It does not parse
YAML; it relies on the lexical surface area of the flag names, which is
narrow enough that real-world FP rates are low.

The detector never calls Prometheus, never reads metrics, never touches the
network.

## False-positive risks

- A doc/comment that warns against these flags by quoting them will be
  flagged. Reviewers should glance at FLAG context.
- An ops runbook YAML that uses the keys `enableAdminAPI: true` outside of a
  Prometheus chart context (e.g. some other tool that happens to share the
  key name) will be flagged. We accept this; cross-referencing the file
  path against `prometheus` directories is the caller's job.
- Signal 3 will fire when a user *intentionally* fronts Prometheus with an
  authenticating reverse proxy on the same host but still binds Prometheus
  itself to `0.0.0.0`. That's a deployment smell on its own; flagging it
  is intended.

## Fixtures

- `fixtures/bad/`: 4 snippets covering each signal.
- `fixtures/good/`: 3 snippets — flags off, loopback-only bind, and a
  reverse-proxy pattern with Prometheus on `127.0.0.1` only.

## Smoke

`bash smoke.sh` asserts `bad=4/4` flagged and `good=0/3` flagged.
