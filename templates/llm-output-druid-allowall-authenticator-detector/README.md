# llm-output-druid-allowall-authenticator-detector

Defensive detector for LLM-generated Apache Druid configurations
that leave the authenticator chain set to the default
`["allowAll"]`. With `allowAll`, **every** HTTP request to the
Druid Router / Broker / Coordinator / Overlord is treated as a
fully privileged user -- arbitrary SQL, ingestion task submission,
datasource drops, and runtime-property changes are all wide
open.

## CWE / OWASP mapping

- **CWE-306**: Missing Authentication for Critical Function
- **CWE-1188**: Insecure Default Initialization of Resource
- **CWE-284**: Improper Access Control
- **OWASP A01:2021** Broken Access Control
- **OWASP A05:2021** Security Misconfiguration

Vendor warning:
<https://druid.apache.org/docs/latest/operations/security-overview>

> "By default, Druid uses the AllowAll Authenticator and the
>  AllowAll Authorizer, which together provide no security."

Real-world impact: CVE-2021-26919 (Druid SQL ingestion-task RCE)
and CVE-2021-25646 (JavaScript-enabled config arbitrary code) both
required the attacker to reach the HTTP API -- which `allowAll`
makes trivial.

## What it flags

A Druid file (sniffed by the presence of `druid.service`,
`druid.host`, `druid.zk.service.host`, `druid.metadata.storage.type`,
or `druid` in the basename) is flagged when EITHER:

1. It explicitly sets the chain to `allowAll`:
   - `druid.auth.authenticatorChain=["allowAll"]` in `.properties`
   - `"druid.auth.authenticatorChain": ["allowAll"]` in JSON
   - `authenticatorChain: allowAll` in YAML / Helm values
   - `-Ddruid.auth.authenticatorChain=["allowAll"]` on a CLI / env

2. It is a Druid `.properties` config that **omits** the chain
   entirely -- in which case the default `allowAll` will apply.

## What it does NOT flag

- Configs that set the chain to a real authenticator
  (`MyBasicAuthenticator`, `MyKerberosAuthenticator`, etc.)
- Comments / docs that mention the bad pattern
- Non-Druid YAML / properties files (the file-type sniff requires
  Druid-specific keys before the missing-chain finding fires)

## Why LLMs ship this

The Druid quickstart and every "spin up Druid in 10 minutes" blog
either omit the auth chain (so the default `allowAll` is in
force) or explicitly set it to `["allowAll"]`. Models replay that
into production runtime properties, helm values, and Dockerfiles.

## Usage

```bash
python3 detect.py path/to/common.runtime.properties
python3 detect.py path/to/repo/   # walks the tree
```

Exit codes: `0` = clean, `1` = findings, `2` = usage error.

## Worked example

```bash
$ bash smoke.sh
bad=4/4 good=0/3
PASS
```

Positive fixtures:

1. `common.runtime.properties` with explicit
   `druid.auth.authenticatorChain=["allowAll"]`
2. JSON config with `"druid.auth.authenticatorChain": ["allowAll"]`
3. Druid `.properties` with **no** chain key (default applies)
4. Launcher script with `-Ddruid.auth.authenticatorChain=["allowAll"]`

Negative fixtures:

1. `.properties` with `["MyBasicAuthenticator"]` and the matching
   `druid-basic-security` extension loaded
2. JSON with `["MyKerberosAuthenticator"]` and `druid-kerberos`
   extension loaded
3. A docs file showing the bad pattern only in `#` comments

## Remediation

Load the `druid-basic-security` extension (or `druid-kerberos`)
and set the chain explicitly. Example:

```properties
druid.extensions.loadList=["druid-basic-security", ...]
druid.auth.authenticatorChain=["MyBasicAuthenticator"]
druid.auth.authenticator.MyBasicAuthenticator.type=basic
druid.auth.authorizers=["MyBasicAuthorizer"]
druid.auth.authorizer.MyBasicAuthorizer.type=basic
druid.escalator.type=basic
```

Plus: never expose Router / Broker ports to untrusted networks
without a TLS-terminating, authenticating proxy.
