# llm-output-aerospike-security-disabled-detector

Stdlib-only Python detector that flags **Aerospike** server
configurations and Docker / Kubernetes / systemd invocations which
explicitly disable the security subsystem — i.e. an
`aerospike.conf` containing `security { enable-security false }`,
the legacy single-line `enable-security false` directive, or env
overrides like `SECURITY_ENABLED=false` consumed by the official
`aerospike/aerospike-server-enterprise` image entrypoint.

With security disabled, every client that can reach the service
port (default 3000) connects with full administrative ReQL-style
access: it can read, write, and drop any namespace, and it can
issue `info` commands that expose the cluster topology and the
XDR pipeline.

Maps to:
- **CWE-306**: Missing Authentication for Critical Function.
- **CWE-1188**: Insecure Default Initialization of Resource.
- **CWE-732**: Incorrect Permission Assignment for Critical Resource.

## Heuristic

We flag any of the following, outside `#` / `//` comment lines:

1. `enable-security false` (or `= false`, `: false`, `0`, `no`,
   `off`) inside a `security { ... }` stanza in an
   `aerospike.conf` — handled by tracking brace depth.
2. Top-level legacy `enable-security false` (Aerospike 5.x
   compatibility form), outside a `security {}` stanza.
3. `SECURITY_ENABLED=false` (or `=0`, `=no`, `=off`) env override
   in a Dockerfile, docker-compose env block, k8s env list, or
   systemd `Environment=` directive — the official enterprise
   image entrypoint reads this var.
4. A `security { ... }` stanza that contains **no** `enable-security`
   key at all — that is documented as "security disabled" because
   the default of the key is `false`. (We only flag this when the
   stanza is otherwise non-empty, to avoid noise on stub configs.)

Each occurrence emits one finding line.

## CWE / standards

- **CWE-306**: Missing Authentication for Critical Function.
- **CWE-1188**: Insecure Default Initialization of Resource.
- **CWE-732**: Incorrect Permission Assignment for Critical Resource.
- Aerospike server reference, `security` stanza: "If
  `enable-security` is `false` (the default), no authentication
  is required and every client request is executed as the
  superuser."

## What we accept (no false positive)

- `security { enable-security true }` (the secure form).
- `SECURITY_ENABLED=true` env override.
- An `aerospike.conf` with no `security` stanza at all **and** no
  `enable-security` key (we can't infer intent — flagging would
  be too noisy on stub configs used in unit tests).
- Documentation / commented-out lines (`# enable-security false`).
- The string `security` in unrelated contexts (e.g. a comment
  about TLS, a label `app.kubernetes.io/component: security`).

## Layout

```
detect.py            stdlib-only scanner (regex over text)
smoke.sh             runs detect.py against examples/ and asserts
examples/bad/        4 fixtures that MUST be flagged
examples/good/       3 fixtures that MUST NOT be flagged
```

## Run

```
python3 detect.py path/to/aerospike.conf
python3 detect.py path/to/repo
bash smoke.sh
```

Exit codes: `0` = clean, `1` = findings, `2` = usage error.

## Why this is a real LLM failure mode

The Aerospike "Getting Started on Docker" guide ships a config
with no `security` stanza, and many tutorials carry that pattern
forward into staging clusters. When users hit the
`AEROSPIKE_ERR_SECURITY_NOT_ENABLED` error after enabling RBAC,
LLMs reliably suggest "set `enable-security false`" or
`SECURITY_ENABLED=false` to "make the error go away", which
silently turns the entire cluster into an anonymous-access
service. The detector exists to catch that paste before it
reaches a Helm chart, an Operator CR, or a GitOps-tracked
manifest.
