# llm-output-grafana-anonymous-org-role-admin-detector

Stdlib-only Python detector that flags **Grafana** deployments where
the **anonymous auth** provider is enabled AND the anonymous user is
granted the `Admin` (or `Editor`) org role. Maps to **CWE-862**
(Missing Authorization), **CWE-1188** (Insecure Default Initialization
of Resource), **CWE-284** (Improper Access Control), OWASP **A01:2021
Broken Access Control**.

Anonymous + `Admin` means anyone who can reach the Grafana HTTP
endpoint -- with no credentials -- can:

- read every dashboard and the configured datasource credentials
  (Grafana exposes datasource secrets in plaintext via the API to
  Admin),
- create / edit / delete dashboards, alerts, and folders,
- add new datasources, install plugins, manage users, change org
  settings,
- in newer Grafana, execute arbitrary SQL against bound datasources
  through the query API.

`auth.anonymous` was designed for **public read-only kiosks** with
`org_role = Viewer`. Promoting the anonymous principal to `Editor` /
`Admin` turns the Grafana instance into an unauthenticated control
plane for whatever it is wired up to.

## Why LLMs ship this

Tutorials say "to make Grafana public, set `[auth.anonymous] enabled =
true` and bump `org_role` so people can edit". The model copies that
into a Helm values file or Docker env block without distinguishing
"public-read kiosk" from "give the internet root on our metrics
stack".

## Heuristic

A finding requires **both** signals in the same file:

1. The anonymous provider enabled, expressed as one of:
   - INI: `[auth.anonymous]` block with `enabled = true|1|yes|on`
   - Env: `GF_AUTH_ANONYMOUS_ENABLED=true`
   - YAML: `anonymous:` (or `auth.anonymous:`) with `enabled: true`

2. The anonymous role escalated, expressed as one of:
   - INI: `org_role = Admin|Editor` inside the same `[auth.anonymous]`
     section
   - Env: `GF_AUTH_ANONYMOUS_ORG_ROLE=Admin|Editor`
   - YAML: `org_role: Admin|Editor` under the same `anonymous:` block

Findings land on the **role-escalation line** (so reviewers see the
escalation, not just the toggle), and reference the line where the
provider was enabled.

## What we accept (no false positive)

- `auth.anonymous` enabled with `org_role = Viewer` (genuine public
  read-only kiosk -- the intended use).
- `auth.anonymous` disabled (`enabled = false`), even if a stray
  `org_role = Admin` is left over.
- `org_role = Admin` for non-anonymous auth providers
  (`[auth.github]`, `[auth.generic_oauth]`, `[users]`,
  `[auth.basic]`) -- those are authenticated principals, different
  threat model.
- README / comments mentioning the bad pattern.

## What we flag

- `grafana.ini` with `[auth.anonymous]` + `enabled = true` +
  `org_role = Admin|Editor`.
- Docker-compose / Dockerfile / k8s manifest setting
  `GF_AUTH_ANONYMOUS_ENABLED=true` and
  `GF_AUTH_ANONYMOUS_ORG_ROLE=Admin|Editor`.
- Helm values nesting `auth.anonymous` (or `anonymous`) with
  `enabled: true` and `org_role: Admin|Editor`.
- systemd unit `Environment=GF_AUTH_ANONYMOUS_ENABLED=true` +
  `Environment=GF_AUTH_ANONYMOUS_ORG_ROLE=Admin`.

## Limits / known false negatives

- We do not flag `org_role` set via Grafana's HTTP API
  (`/api/org/users`) at runtime -- only declarative config.
- We do not flag a custom reverse-proxy pattern that injects a real
  user header and then sets anonymous Admin "behind" the proxy. That
  pattern is actually a separate anti-pattern (proxy auth bypass), and
  is covered elsewhere.
- We require `enabled = true` and `org_role` in the **same file**.
  Cross-file (e.g. base ini + helm overlay) escalations are out of
  scope for a stdlib-only static check.

## Usage

```bash
python3 detect.py path/to/grafana.ini
python3 detect.py path/to/repo/
```

Exit codes: `0` = no findings, `1` = findings (printed to stdout),
`2` = usage error.

## Worked example

```
$ bash smoke.sh
bad=6/6 good=0/6
PASS

$ python3 detect.py examples/bad/01_grafana_ini_admin.ini
examples/bad/01_grafana_ini_admin.ini:11: grafana [auth.anonymous] enabled (line 9) with org_role=Admin (CWE-862/CWE-1188): unauthenticated Admin access

$ python3 detect.py examples/bad/03_compose_env_admin.yaml
examples/bad/03_compose_env_admin.yaml:9: GF_AUTH_ANONYMOUS_ENABLED=true (line 8) and GF_AUTH_ANONYMOUS_ORG_ROLE=Admin -> unauthenticated Admin access (CWE-862/CWE-1188)

$ python3 detect.py examples/bad/05_helm_values.yaml
examples/bad/05_helm_values.yaml:12: grafana anonymous: block enabled (line 10) with org_role=Admin (CWE-862/CWE-1188): unauthenticated Admin access

$ python3 detect.py examples/good/01_anon_viewer_only.ini
$ echo $?
0
```

Layout:

```
examples/bad/
  01_grafana_ini_admin.ini       # [auth.anonymous] enabled + org_role=Admin
  02_grafana_ini_editor.ini      # [auth.anonymous] enabled + org_role=Editor
  03_compose_env_admin.yaml      # GF_AUTH_ANONYMOUS_* env pair
  04_dockerfile_env.Dockerfile   # ENV GF_AUTH_ANONYMOUS_ENABLED + ORG_ROLE
  05_helm_values.yaml            # helm grafana.ini auth.anonymous block
  06_systemd_env.service         # systemd Environment= pair
examples/good/
  01_anon_viewer_only.ini        # anonymous on, role=Viewer (intended)
  02_anon_disabled.ini           # anonymous explicitly disabled
  03_compose_no_anon.yaml        # GF_AUTH_ANONYMOUS_ENABLED=false
  04_helm_anon_viewer.yaml       # helm anon role Viewer
  05_doc_only_in_comments.yaml   # bad pattern only in YAML comments
  06_dockerfile_no_anon.Dockerfile  # production Dockerfile w/ admin pw secret
```
