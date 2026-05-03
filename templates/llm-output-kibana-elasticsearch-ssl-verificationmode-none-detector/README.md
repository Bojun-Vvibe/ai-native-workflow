# llm-output-kibana-elasticsearch-ssl-verificationmode-none-detector

Detects LLM-emitted Kibana configurations that disable TLS verification on
the Elasticsearch backend connection by setting
`elasticsearch.ssl.verificationMode: none`. With verification turned off,
Kibana accepts any certificate (including expired, self-signed, or
attacker-presented ones) on the link to the Elasticsearch cluster, allowing
a network-position adversary to silently MITM all index queries, dashboards,
and credentials.

The supported settings are `full` (cert + hostname) and `certificate` (cert
only); only `none` is dangerous. LLMs frequently emit `none` from quickstart
snippets when self-signed development certs cause "unable to verify" errors.

## What this catches

| # | Pattern                                                                                        |
|---|------------------------------------------------------------------------------------------------|
| 1 | `kibana.yml`: `elasticsearch.ssl.verificationMode: none` (any spacing, any quoting)            |
| 2 | Env var `ELASTICSEARCH_SSL_VERIFICATIONMODE=none` in systemd, Dockerfile, .env-style files     |
| 3 | docker-compose / k8s manifest passing the env var or mounting a `kibana.yml` containing `none` |
| 4 | Helm values: `kibanaConfig` block (or extraEnvs) configuring verificationMode to none          |

CWE-295 (Improper Certificate Validation).

## Usage

```bash
./detector.sh examples/bad/* examples/good/*
```

Exit 0 iff every bad sample fires and zero good samples fire. The trailing
status line is `bad=N/N good=0/M PASS|FAIL`.

## Worked example

Run `./run-test.sh` from this directory. It runs the detector against the
bundled samples and asserts `bad=4/4 good=0/3 PASS`.
