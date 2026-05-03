# llm-output-qdrant-no-api-key-detector

Detect Qdrant configurations and launch scripts that expose the HTTP/gRPC
API without an API key. When `service.api_key` is unset (or empty) and the
service binds to `0.0.0.0`, every collection — including vectors that may
encode private text — is reachable by any client that can reach port `6333`
or `6334`. LLMs often produce "minimal" Qdrant snippets that omit the key
entirely.

## What bad LLM output looks like

`config.yaml` exposing the service publicly with no key:

```yaml
service:
  host: 0.0.0.0
  http_port: 6333
  # api_key: (left blank for now)
```

A compose file that publishes both ports with no `QDRANT__SERVICE__API_KEY`:

```yaml
services:
  vectors:
    image: qdrant/qdrant:v1.12.0
    ports: ["6333:6333", "6334:6334"]
```

An env script that explicitly empties the key:

```sh
export QDRANT__SERVICE__API_KEY=""
docker run -p 6333:6333 qdrant/qdrant:v1.12.0
```

TLS off, public bind, no key:

```yaml
service:
  host: 0.0.0.0
  enable_tls: false
```

## What good LLM output looks like

API key sourced from env in config:

```yaml
service:
  host: 0.0.0.0
  http_port: 6333
  api_key: "${QDRANT_API_KEY}"
  enable_tls: true
```

Compose with the key wired through:

```yaml
services:
  vectors:
    image: qdrant/qdrant:v1.12.0
    environment:
      QDRANT__SERVICE__API_KEY: "${QDRANT_API_KEY}"
```

Or simply pinned to loopback:

```yaml
service:
  host: 127.0.0.1
```

## Run the smoke test

```sh
bash detect.sh samples/bad/* samples/good/*
```

Expected:

```
bad=4/4 good=0/3 PASS
```

Exit status is `0` only when every bad sample is flagged and zero good
samples are flagged.

## Detector rules

1. Config binding `host: 0.0.0.0` with no non-empty `api_key:` value.
2. Container manifest exposing `6333` or `6334` with no
   `QDRANT__SERVICE__API_KEY` env var anywhere in the file.
3. Shell / env file that sets `QDRANT__SERVICE__API_KEY=""`.
4. `enable_tls: false` plus `host: 0.0.0.0` plus no `api_key:` in the same
   file.
