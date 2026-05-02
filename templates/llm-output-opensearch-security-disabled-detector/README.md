# llm-output-opensearch-security-disabled-detector

Static lint that flags OpenSearch / OpenSearch Dashboards configs
(opensearch.yml, opensearch_dashboards.yml, docker-compose envs)
that disable the bundled OpenSearch Security plugin.

`plugins.security.disabled: true` in `opensearch.yml`, or the env var
`DISABLE_SECURITY_PLUGIN=true` in a docker-compose file, switches off
all authentication, TLS-on-transport, audit logging, and role-based
access. Anyone who can reach port 9200 can read every index and
delete the cluster with one HTTP DELETE. LLMs asked "give me a quick
docker-compose for OpenSearch" or "why is my client getting an SSL
error from OpenSearch" routinely emit this shape because it is the
single-line fix that gets a curl `GET /` to return 200.

## Why LLMs emit this

* The official OpenSearch quick-start docker-compose for single-node
  dev uses `DISABLE_SECURITY_PLUGIN=true` + `DISABLE_INSTALL_DEMO_CONFIG=true`,
  and that snippet is the most-copied OpenSearch artifact on the web.
* When users hit the demo-cert chain on first boot, the most common
  Stack Overflow accepted answer is "just disable the security plugin".
* Tutorials targeting OpenSearch Dashboards similarly disable the
  Dashboards-side plugin (`opensearch_security.disabled: true`) to
  silence the login screen.

## What it catches

Per file (line-level):

- `plugins.security.disabled: true` (opensearch.yml)
- `opensearch_security.disabled: true` (opensearch_dashboards.yml)
- `DISABLE_SECURITY_PLUGIN=true` env-var (compose / .env, quoted or not)
- `DISABLE_SECURITY_DASHBOARDS_PLUGIN=true` env-var
- `plugins.security.ssl.http.enabled: false` (HTTP TLS off)
- `plugins.security.allow_default_init_securityindex: true` paired
  with `plugins.security.allow_unsafe_democertificates: true`
  (demo certs in a non-loopback config)

Per file (whole-file):

- An `opensearch.yml` with `network.host` bound to a non-loopback
  address AND no `plugins.security.ssl.transport.enabled: true` AND
  no `plugins.security.disabled: false` directive.

## What it does NOT flag

- `plugins.security.disabled: false` — explicit enable.
- `network.host: 127.0.0.1` / `localhost` only — loopback is fine.
- Lines with a trailing `# os-sec-ok` comment.
- Files containing `# os-sec-ok-file` anywhere.
- Blocks bracketed by `# os-sec-ok-begin` / `# os-sec-ok-end`.

## How to detect (the pattern)

```sh
python3 detector.py path/to/configs/
```

Exit code = number of files with at least one finding (capped at
255). Stdout: `<file>:<line>:<reason>`.

## Safe pattern

```yaml
# opensearch.yml
network.host: 0.0.0.0
plugins.security.disabled: false
plugins.security.ssl.transport.enabled: true
plugins.security.ssl.http.enabled: true
plugins.security.allow_unsafe_democertificates: false
```

with real certs provisioned via `securityadmin.sh` and an
internal-users / roles_mapping pair under `config/opensearch-security/`.

## Refs

- CWE-306: Missing Authentication for Critical Function
- CWE-1188: Insecure Default Initialization of Resource
- OpenSearch Security plugin docs — "Disable security" warning
- CVE-2021-44832 (Elasticsearch / OpenSearch lineage — auth bypass
  classes that this plugin exists to prevent)

## Verify

```sh
bash verify.sh
```

Should print `bad=5/5 good=0/3 PASS`.
