# llm-output-alertmanager-config-reload-public-bind-detector

## Purpose

Alertmanager exposes `POST /-/reload` (config hot-reload) and `POST /-/quit`
(shutdown) on its HTTP listener. Alertmanager itself has no built-in
authentication for these endpoints — anyone who can reach the listener
can force a config reload (causing `Loading new configuration` churn,
silencing changes, or DoS via repeated reloads) or terminate the process.

When an LLM is asked "let our CI hot-reload alertmanager" or "make
alertmanager listen on the LAN", it commonly proposes binding
`--web.listen-address` to `0.0.0.0` (or omitting the bind, which defaults
to all interfaces) without putting an authenticating reverse proxy in
front. The fix is to bind to loopback only, or front Alertmanager with an
auth proxy on a separate listener.

## Signals (any one is sufficient to flag)

1. `alertmanager` binary (or `alertmanager` systemd `ExecStart=`) invoked
   with `--web.listen-address` bound to `0.0.0.0`, `[::]`, or any
   non-loopback IPv4 literal.
2. Docker / docker-compose / Kubernetes `command:` or `args:` array for
   an `alertmanager` image that contains `--web.listen-address=0.0.0.0:`
   (or omits the flag entirely while publishing port 9093 — we
   approximate this by flagging `--cluster.listen-address` patterns
   alongside a missing loopback bind, see signal 3).
3. `--web.external-url` set to a non-loopback URL **and** no
   `--web.route-prefix` indicating an upstream reverse-proxy mount
   point — this is a strong "exposed directly" smell.
4. Helm-style `values.yaml` with `alertmanager.service.type: LoadBalancer`
   or `NodePort` (literal match) — direct cluster-external exposure of
   the management endpoints.

## How the detector works

`detector.sh` performs targeted `grep -nE` passes per signal and emits
one `FLAG <signal-id> <file>:<lineno> <text>` line per finding. It does
not parse YAML; it relies on the lexical surface of the flag and key
names. The detector never calls Alertmanager and never touches the
network.

## False-positive risks

- A doc/comment that quotes the dangerous pattern verbatim will be
  flagged. Reviewers should glance at FLAG context.
- Signal 4 will fire when a chart user *intentionally* exposes
  Alertmanager via LoadBalancer behind a separate ingress with auth.
  That is a deployment smell on its own; flagging it is intended.
- Signal 3 cannot tell a true public URL from a private DNS name. We
  conservatively skip URLs whose host is `localhost`, `127.*`, or
  `*.internal`.

## Fixtures

- `fixtures/bad/`: 4 snippets covering each signal.
- `fixtures/good/`: 3 snippets — loopback bind, route-prefix behind
  proxy, and ClusterIP-only Helm values.

## Smoke

`bash smoke.sh` asserts `bad=4/4` flagged and `good=0/3` flagged.

## References

- Alertmanager management API: `/-/reload`, `/-/quit` are unauthenticated.
- CWE-306: Missing Authentication for Critical Function.
