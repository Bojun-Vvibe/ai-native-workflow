# llm-output-opensearch-dashboards-security-disabled-detector

Detects OpenSearch Dashboards (`opensearch_dashboards.yml`) configs
that disable or bypass the Security plugin's UI-side authentication
while the Dashboards instance is bound on a non-loopback interface.

## Why this matters

Even when the OpenSearch *cluster* is properly secured, the Dashboards
front-end is the day-to-day human entry point. A Dashboards instance
configured with any of:

* `opensearch_security.disabled: true`
* `opensearch_security.auth.type: ""` (or `"none"`) with no SAML/OIDC/
  JWT/basicauth backend configured
* `opensearch.username` / `opensearch.password` left at the shipped
  service-account defaults (`kibanaserver` / `admin`)
* `server.ssl.enabled: false` while `server.host` is bound publicly

…hands every browser that reaches port 5601 an interactive session
running as the configured service account. From there, the attacker
gets full read access to every index the service account can see,
including raw audit logs and any saved searches that pin sensitive
filters into URLs.

These misconfigurations are common because Dashboards' upstream "first
boot" tutorials disable the Security plugin to avoid TLS setup, and
operators forget to re-enable it before exposing the UI on a private
network (which is rarely as private as assumed).

## What this detector matches

For each scanned `*.yml` / `*.yaml` (especially
`opensearch_dashboards.yml`):

| Rule | Trigger |
|------|---------|
| 1 | `opensearch_security.disabled: true` AND `server.host` is not loopback |
| 2 | `opensearch_security.auth.type` is empty / `none` AND no `openid.*` / `saml.*` / `jwt.*` / `proxycache.*` / `basicauth.*` keys present |
| 3 | `opensearch.username` ∈ {`kibanaserver`, `admin`, `opensearch_dashboards_user`} AND `opensearch.password` ∈ {`kibanaserver`, `admin`, `changeme`, `password`} |
| 4 | `server.ssl.enabled: false` AND `server.host` is not loopback |

A binding is "not loopback" when `server.host` is unset, `0.0.0.0`,
`::`, `*`, or any non-`127.0.0.1` / non-`::1` / non-`localhost` value.

### Ignored (good)

* `server.host` set to `127.0.0.1` / `::1` / `localhost` (rules 1–3
  silenced; rule 4 cannot fire because the bind isn't remote).
* Security plugin enabled with at least one configured auth backend.
* Lines carrying the inline marker `# osd-security-disabled-allowed`.

The detector does line-by-line key parsing — no full YAML parser — so
it tolerates inline comments, quoted/unquoted scalars, and dotted-key
shorthand without dragging in a YAML dependency.

## Usage

```
python3 detector.py path/to/opensearch_dashboards.yml [more paths ...]
```

Exit code is the number of files with at least one finding (capped at
255). Stdout lines have the form `<file>:<line>:<reason>`.

## Worked example

```
$ ./verify.sh
bad=4/4 good=0/4
PASS
```

Per-file detector output:

```
--- examples/bad/01_security_disabled_true.yml ---
examples/bad/01_security_disabled_true.yml:9:opensearch_security.disabled is true — Security plugin bypassed on a non-loopback Dashboards binding
exit=1
--- examples/bad/02_auth_type_empty_no_backend.yml ---
examples/bad/02_auth_type_empty_no_backend.yml:8:opensearch_security.auth.type is empty/none with no openid/saml/jwt/proxycache/basicauth backend configured
exit=1
--- examples/bad/03_default_service_creds.yml ---
examples/bad/03_default_service_creds.yml:6:opensearch.username='kibanaserver' reuses the default service account with default password 'kibanaserver'
exit=1
--- examples/bad/04_tls_off_public_bind.yml ---
examples/bad/04_tls_off_public_bind.yml:5:server.ssl.enabled=false while server.host='10.50.12.4' is not loopback — Dashboards session cookie travels in cleartext
exit=1
--- examples/good/01_loopback_sandbox.yml ---
exit=0
--- examples/good/02_oidc_enabled.yml ---
exit=0
--- examples/good/03_saml_enabled.yml ---
exit=0
--- examples/good/04_dev_suppressed.yml ---
exit=0
```

## Remediation

* Re-enable Security: remove `opensearch_security.disabled: true`.
* Wire a real auth backend (`openid`, `saml`, `jwt`, `proxycache`, or
  upstream-managed basic auth with rotated passwords) — the auth type
  should never be `""` / `"none"` on a publicly-bound instance.
* Replace any default service-account credentials with rotated secrets
  delivered via Vault Agent / K8s `secretKeyRef` / a sealed secret.
* Set `server.ssl.enabled: true` and provision certificates whenever
  `server.host` is anything other than loopback.
* Add `# osd-security-disabled-allowed` only on developer fixtures that
  are intentionally loopback-bound and never deployed.
