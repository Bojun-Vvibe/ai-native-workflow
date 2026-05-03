# llm-output-typesense-no-api-key-detector

Detects LLM-emitted Typesense search server configurations and launch commands
that disable or skip the admin API key while exposing the HTTP listener
publicly. Typesense uses a single mandatory `--api-key` flag (or
`TYPESENSE_API_KEY` env var) as the bootstrap admin credential. If it is
empty, missing, or set to the documentation default `xyz`, anyone reaching
port 8108 can read/write any collection.

## What this catches

| # | Pattern                                                                                                       |
|---|---------------------------------------------------------------------------------------------------------------|
| 1 | `typesense-server` invocation (CLI, Dockerfile `CMD`, systemd unit) without any `--api-key` / `-k` flag       |
| 2 | `--api-key=""` or `--api-key=` (empty value)                                                                  |
| 3 | `TYPESENSE_API_KEY=""` env export, or `TYPESENSE_API_KEY=xyz` (the docs sample value)                         |
| 4 | docker-compose / k8s manifest exposing port 8108 on a non-loopback bind without a non-empty `TYPESENSE_API_KEY` |

CWE-306 (Missing Authentication for Critical Function) and CWE-798
(Use of Hard-coded Credentials, when the docs default `xyz` is shipped).

## Usage

```bash
./detector.sh examples/bad/*  examples/good/*
```

Exit 0 iff every bad sample fires and zero good samples fire. The trailing
status line is `bad=N/N good=0/M PASS|FAIL`.

## Worked example

Run `./run-test.sh` from this directory. It runs the detector against the
bundled samples and asserts `bad=4/4 good=0/3 PASS`.
