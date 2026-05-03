# llm-output-nomad-acl-disabled-detector

Flags HashiCorp Nomad configurations that disable ACLs or run the
agent in `-dev` mode — the equivalent of running a cluster scheduler
with no authentication on its HTTP API (default `:4646`).

## What it catches

- HCL: `acl { enabled = false }`
- JSON: `"acl": {"enabled": false}`
- YAML / Helm values: `acl: { enabled: false }`
- CLI / compose / Dockerfile / systemd: `nomad agent -dev`,
  `nomad agent -dev-connect`

## Why it's risky

A Nomad agent without ACLs lets any network-reachable client:

- submit, stop, or modify any job (full RCE on the cluster nodes
  via job exec / raw_exec / docker drivers),
- read job specs, which routinely contain secrets via `template`
  stanzas or environment variables,
- exec into running allocations (`nomad alloc exec`),
- read the entire Raft state including operator tokens.

Nomad's own docs require ACLs in production with a deny-by-default
policy. See <https://developer.hashicorp.com/nomad/tutorials/access-control>.

Maps to **CWE-306** (Missing Authentication for Critical Function),
**CWE-732** (Incorrect Permission Assignment for Critical Resource),
**CWE-1188** (Insecure Default Initialization of Resource), and
**OWASP A05:2021** Security Misconfiguration.

## Why LLMs ship this

Every "Nomad in 5 minutes" tutorial uses `nomad agent -dev` or
`acl { enabled = false }` so the demo Just Works without bootstrap.
Models lift the block straight into a production `nomad.hcl` /
docker-compose / k8s manifest.

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
`Dockerfile*`, `docker-compose.*`, and any file whose basename
starts with `nomad`.

## Smoke test

```bash
./smoke.sh
# bad=N/N good=0/M
# PASS
```

## What it does NOT flag

- Configs that omit the `acl` block entirely (could be set elsewhere
  or in an environment-specific overlay; we don't want to spam).
- `acl { enabled = true }` (the correct pattern).
- Comments / docs that mention the bad pattern.
