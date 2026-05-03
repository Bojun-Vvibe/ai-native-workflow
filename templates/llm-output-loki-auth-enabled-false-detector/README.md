# llm-output-loki-auth-enabled-false-detector

Flags Grafana Loki configurations that set `auth_enabled: false` (YAML)
or pass `-auth.enabled=false` on the CLI.

## What it detects

Loki has no built-in authentication. The `auth_enabled` flag does **not**
turn on auth — it tells Loki to **trust the `X-Scope-OrgID` header** from
the caller for tenant routing. Setting it to `false` makes Loki
single-tenant (`fake` tenant) and accepts every push/query/delete from
anyone who can reach the HTTP port (default `:3100`).

Concrete bad patterns flagged:

1. YAML top-level key: `auth_enabled: false`
2. CLI flag: `loki -auth.enabled=false` / `--auth.enabled=false`
3. Helm values block: `loki:\n  auth_enabled: false`

## Why this is dangerous

Anyone with network reach to Loki can:

- push arbitrary log lines into any tenant (SIEM poisoning, alert noise)
- query every tenant's logs (stack traces, JWTs, request bodies, PII)
- delete log series via the compactor delete API
- enumerate labels to map internal topology

## CWE / OWASP refs

- **CWE-306**: Missing Authentication for Critical Function
- **CWE-862**: Missing Authorization
- **CWE-1188**: Insecure Default Initialization of Resource
- **OWASP A05:2021** — Security Misconfiguration

Upstream warning:
<https://grafana.com/docs/loki/latest/operations/authentication/>

## False positives

The detector requires the file to "look like" a Loki config — either the
filename hints at Loki (`loki*.yaml`, `local-config.yaml`,
`loki-values.yaml`) or the file contains a Loki-specific top-level key
(`ingester:`, `schema_config:`, `ruler:`, `compactor:`,
`frontend_worker:`, etc.) or a top-level `loki:` block (Helm values).

CLI matches additionally require the literal token `loki` on the same
line, so unrelated `-auth.enabled=false` flags from other binaries are
not flagged.

Comments are ignored. `auth_enabled: true` is never flagged.

## Usage

```sh
python3 detect.py path/to/loki-config.yaml
python3 detect.py path/to/dir/
```

Exit codes: `0` clean, `1` findings, `2` usage error.

## Verify

```sh
bash smoke.sh
# bad=4/4 good=0/3
# PASS
```
