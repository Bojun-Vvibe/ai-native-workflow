# llm-output-elasticsearch-xpack-security-disabled-detector

Detects LLM-emitted Elasticsearch configs, Dockerfiles, and compose
files that explicitly disable X-Pack security, leaving the cluster
unauthenticated — the canonical "Elastic ransom" exposure pattern.

Three forms are matched:
- `xpack.security.enabled: false` in `elasticsearch.yml`
- `xpack.security.enabled=false` as an env var (compose `environment:`,
  Dockerfile `ENV`, shell `export`, JVM `-E` flag)
- security on but BOTH transport and http SSL disabled — credentials
  in cleartext on the wire, equivalent risk profile

CWE-306 (Missing Authentication for Critical Function) and CWE-319
(Cleartext Transmission of Sensitive Information) for the SSL-off case.

## What this catches

| # | Pattern                                                                                  |
|---|------------------------------------------------------------------------------------------|
| 1 | `xpack.security.enabled: false` in YAML config                                           |
| 2 | `xpack.security.enabled: true` with both `http.ssl.enabled` and `transport.ssl.enabled` false |
| 3 | `xpack.security.enabled=false` (or `.http.ssl.enabled=false` / `.transport.ssl.enabled=false`) in env / CLI / Dockerfile form |
| 4 | `discovery.type=single-node` combined with `xpack.security.enabled=false` (LLM "local dev" pattern that escapes to staging) |

## Usage

```bash
python3 detector.py examples/bad/* examples/good/*
```

Exit 0 iff every bad sample fires and zero good samples fire. Final
stdout line: `bad=N/N good=0/M PASS|FAIL`.

## Worked example

Run `./run-test.sh` from this directory. It executes the detector
against the bundled samples and asserts `bad=4/4 good=0/4 PASS`.
