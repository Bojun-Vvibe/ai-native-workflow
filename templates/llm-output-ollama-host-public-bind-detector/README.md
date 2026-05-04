# llm-output-ollama-host-public-bind-detector

Detects [Ollama](https://github.com/ollama/ollama) configurations
that bind the model API to a non-loopback address via
`OLLAMA_HOST`. Ollama has no built-in authentication and no TLS,
so any non-loopback bind hands the API to anyone reachable on
the listen port.

## What it flags

`OLLAMA_HOST=<value>` set to a public bind in:

- env-style files (`.envfile`, `.environment`, systemd
  `EnvironmentFile=` targets)
- shell scripts (`export OLLAMA_HOST=...`,
  inline `OLLAMA_HOST=... ollama serve`)
- systemd units (`Environment="OLLAMA_HOST=..."`)
- Dockerfiles (`ENV OLLAMA_HOST=...` and the space-form
  `ENV OLLAMA_HOST 0.0.0.0:11434`)
- docker-compose YAML `environment:` blocks (both mapping form
  `OLLAMA_HOST: 0.0.0.0:11434` and list form
  `- OLLAMA_HOST=0.0.0.0:11434`)

Public-bind heuristics: bare `:port`, bare port number, `0.0.0.0`
(with or without port), `*` / `*:port`, `[::]`/`[::]:port`, or any
non-loopback hostname / IP. Loopback values
(`127.0.0.1`, `localhost`, `::1`, `[::1]`) are not flagged.

## Why it matters

A public Ollama port lets unauthenticated callers:

- run inference on any pulled model (GPU/CPU burn, electricity)
- pull arbitrary multi-GB models from the default registry
  (disk + egress amplification)
- delete or copy local models
- enumerate the model inventory via `/api/show` and `/api/tags`
- use the host as a free, attributable LLM gateway

The README and many issues are explicit that the API is meant for
localhost. The most copy-pasted homelab snippet is exactly the
one this detector catches:

```
OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

CWE-306 (Missing Authentication for Critical Function),
CWE-668 (Exposure of Resource to Wrong Sphere),
CWE-770 (Allocation of Resources Without Limits or Throttling).
OWASP A01:2021 / A05:2021.

## Usage

```
python3 detect.py <file-or-dir> [more...]
```

Exit codes: `0` clean, `1` findings, `2` usage error.

```
$ python3 detect.py examples/bad/
examples/bad/01_systemd.envfile:3: ollama `OLLAMA_HOST=0.0.0.0:11434` -> ...
examples/bad/02_launch.sh:4: ollama `OLLAMA_HOST=0.0.0.0` -> ...
examples/bad/03_Dockerfile:2: ollama `OLLAMA_HOST=0.0.0.0:11434` -> ...
examples/bad/04_docker-compose.yml:8: ollama yaml `OLLAMA_HOST: 0.0.0.0:11434` -> ...
```

## Verify

```
./smoke.sh    # bad=4/4 good=0/4 PASS
```

## How to fix

- Bind to `127.0.0.1` (default behaviour without `OLLAMA_HOST`).
- For remote access, terminate at an authenticating reverse proxy
  (oauth2-proxy, an SSO ingress, mTLS, a VPN, an SSH tunnel).
- Pair with rate-limiting and disk quotas so a single client cannot
  burn the GPU or fill the disk by pulling models.

## Limitations

- Stdlib only; no full YAML parsing. Flow-style mappings like
  `{OLLAMA_HOST: "0.0.0.0:11434"}` are not handled.
- A value like `OLLAMA_HOST=$BIND` referencing another env var is
  not resolved; we do not follow shell expansion.
- Examples use `.envfile` / `.environment` extensions (the repo's
  pre-push guardrail forbids `.env`).
