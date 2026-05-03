# llm-output-meilisearch-no-master-key-detector

Detect Meilisearch configurations and launch scripts that run without a master
key. When `MEILI_MASTER_KEY` (or `--master-key`) is unset or empty, every API
route — including `/keys`, `/indexes`, and document writes — is unauthenticated.
LLMs frequently emit "quick start" snippets that omit the key, then leave the
production deployment open to anyone who can reach port `7700`.

## What bad LLM output looks like

Empty key in an env file:

```sh
export MEILI_MASTER_KEY=""
export MEILI_ENV="production"
./meilisearch
```

Production config with the key commented out:

```toml
env = "production"
http_addr = "0.0.0.0:7700"
# master_key = "set-me-later"
```

A compose file exposing `7700` with no key env at all:

```yaml
services:
  search:
    image: getmeili/meilisearch:v1.10
    ports: ["7700:7700"]
    environment:
      MEILI_ENV: "production"
```

A bare CLI invocation with no key:

```sh
./meilisearch --http-addr 0.0.0.0:7700 --env production
```

## What good LLM output looks like

Key passed via flag from a secret file:

```sh
KEY="$(cat /run/secrets/meili_master_key)"
./meilisearch --master-key "${KEY}"
```

Or set in config:

```toml
env = "production"
master_key = "ZmFrZS1tYXN0ZXIta2V5LWZvci1leGFtcGxlLW9ubHk"
```

## Run the smoke test

```sh
bash detect.sh samples/bad/* samples/good/*
```

Expected:

```
bad=4/4 good=0/3 PASS
```

Exit status is `0` only when every bad sample fires and zero good samples fire.

## Detector rules

1. `MEILI_MASTER_KEY` or `--master-key` set to the empty string.
2. Config file declaring `env = "production"` without a non-empty
   `master_key = "..."`.
3. Container manifest exposing port `7700` with no `MEILI_MASTER_KEY` env
   anywhere in the file.
4. A `meilisearch` CLI invocation with no `--master-key` flag and no
   `MEILI_MASTER_KEY=...` assignment in the same file.
