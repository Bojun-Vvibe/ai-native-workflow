# llm-output-consul-acl-disabled-detector

Flags HashiCorp Consul configurations that disable ACLs or set the
default policy to `allow` — the equivalent of running a key-value
store, service catalog, and service-mesh control plane with no
authentication.

## What it catches

- HCL: `acl { enabled = false }` or `acl { default_policy = "allow" }`
- JSON: `"acl": {"enabled": false}` / `"acl": {"default_policy": "allow"}`
- YAML / Helm values with the same shape
- CLI / compose / Dockerfile / systemd: `consul agent -dev`

## Why it's risky

A Consul agent with ACLs disabled (or in default-allow mode) lets any
network-reachable client:

- read every KV pair (often used as an app-config + secret store),
- register or deregister services (full service-mesh hijack),
- read the catalog of every node, service, IP, and health check,
- snapshot the whole Raft state.

Consul's own docs require `default_policy = "deny"` in production.
See <https://developer.hashicorp.com/consul/docs/security/acl>.

Maps to **CWE-306** (Missing Authentication for Critical Function),
**CWE-732** (Incorrect Permission Assignment for Critical Resource),
**CWE-1188** (Insecure Default Initialization of Resource), and
**OWASP A05:2021** Security Misconfiguration.

## Why LLMs ship this

Every "Consul in 5 minutes" tutorial uses `consul agent -dev` or
`acl { enabled = false }` so the demo Just Works. Models lift that
block straight into a production `consul.hcl` / docker-compose / k8s
manifest.

## Usage

```bash
python3 detect.py path/to/config-or-dir
```

Exit codes:

- `0` — clean
- `1` — at least one finding (one line per finding on stdout)
- `2` — usage error

Stdlib-only, no deps. Walks directories and scans `*.hcl`, `*.json`,
`*.yaml`, `*.yml`, `*.env`, `*.sh`, `*.bash`, `*.service`,
`Dockerfile*`, `docker-compose.*`, and any file whose basename starts
with `consul`.

## Smoke test

```bash
./smoke.sh
# bad=N/N good=0/M
# PASS
```

## What it does NOT flag

- Configs that omit the `acl` block entirely (could be set elsewhere
  or in an environment-specific overlay; we don't want to spam).
- `acl { enabled = true; default_policy = "deny" }` (the correct
  pattern).
- Comments / docs that mention the bad pattern.
