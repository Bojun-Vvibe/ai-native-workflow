# llm-output-nacos-default-credentials-detector

Flags Nacos (Alibaba's service-discovery + dynamic-config server)
configurations that ship the **well-known default** console
credentials:

```
username: nacos
password: nacos
```

These literals appear in the official Nacos quickstart, the bundled
`application.properties` of `nacos/nacos-server`, and almost every
"set up Nacos in 5 minutes" blog. LLMs reproduce them verbatim when
asked to "deploy Nacos" or "wire Spring Cloud to Nacos".

## What it detects

Three concrete forms, all gated by an in-file Nacos context token
(`nacos`, `NACOS_`, `spring.cloud.nacos`, `nacos-server`,
`com.alibaba.nacos`):

1. YAML / properties: `username: nacos` paired with `password: nacos`
   within a 6-line window.
2. Env / docker-compose: `NACOS_AUTH_USERNAME=nacos` /
   `NACOS_AUTH_PASSWORD=nacos`.
3. Spring config: `spring.cloud.nacos.config.username=nacos` plus the
   matching password line.
4. Bare basic-auth literals in shell / curl / Dockerfile commands:
   `-u nacos:nacos` and `://nacos:nacos@host`.

## Why this is dangerous

Anyone who knows the published default (i.e. anyone who has read the
Nacos docs) can hit `/nacos/` and:

- read every dynamic config -- DB connection strings, AK/SK pairs,
  third-party API tokens, feature flags -- in plaintext;
- hijack the service registry by registering a malicious instance
  under an existing service name (classic service-discovery
  poisoning -- all consumer RPCs flow to the attacker);
- modify any consumer's runtime behaviour via config push (RCE-
  adjacent on Spring Cloud apps via SpEL injection in pushed config
  values, see the CVE-2021-29441 / CVE-2021-29442 family);
- create a tenant-level admin and persist access across restarts.

## CWE / OWASP refs

- **CWE-798**: Use of Hard-coded Credentials
- **CWE-1392**: Use of Default Credentials
- **CWE-521**: Weak Password Requirements
- **CWE-1188**: Insecure Default Initialization of Resource
- **OWASP A07:2021** -- Identification and Authentication Failures

## False positives

Skipped:

- Files with no Nacos context tokens at all.
- Comment-only mentions (`# username=nacos password=nacos` in
  documentation).
- A `username: nacos` paired with a non-default password (no match
  unless the password is the literal `nacos`).

## Run

```
python3 detect.py path/to/file-or-dir [more...]
```

Exit codes: `0` clean, `1` findings, `2` usage error.

## Worked example

```
$ ./smoke.sh
bad=4/4 good=0/3
PASS
```

The four `examples/bad/` files (Spring Cloud `application.yml`,
`docker-compose.yml`, `bootstrap.properties`, `provision.sh`) each
trip the detector. The three `examples/good/` files (env-templated
docker-compose, env-templated `bootstrap.properties`, and an
`application.yml` that only mentions the defaults in a comment but
uses real injected creds) all stay clean.
