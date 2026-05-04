# llm-output-docker-registry-no-auth-htpasswd-detector

Detects Docker `registry:2` (CNCF distribution/distribution)
deployments shipped without any authentication backend configured.

## What it flags

Two surfaces:

1. **Registry config files** (`config.yml`, `*registry*.yml`, etc.,
   recognised by the presence of top-level `version:` plus
   `storage:` or `http:`):

   - `auth:` block missing entirely
   - `auth: {}` (empty mapping)
   - `auth: { silly: ... }` or `auth: { none: ... }`
     (explicit no-auth backends)

2. **`docker-compose.*.yml`** services using
   `image: registry:*` or `image: distribution/distribution:*`
   without:
   - `REGISTRY_AUTH=htpasswd` / `REGISTRY_AUTH=token`
   - `REGISTRY_AUTH_TOKEN_REALM` env var
   - mounting `/auth/htpasswd` *with* the corresponding env var

A bare `/auth/htpasswd` mount without the env var is also flagged
because the registry will start with auth disabled (the env var is
what selects the backend).

## Why it matters

The official `registry:2` image ships with an empty `auth:` block in
its baked-in `/etc/docker/registry/config.yml`. With no auth:

- anyone reachable to the listen address can `docker push` and
  `docker pull` any tag,
- `GET /v2/_catalog` lists every repository,
- `DELETE /v2/<name>/manifests/<reference>` (when `delete.enabled`)
  destroys images.

This is exactly the "5 minute self-hosted registry" tutorial that
LLM coding assistants reproduce verbatim.

CWEs: CWE-306 (Missing Authentication for Critical Function),
CWE-287 (Improper Authentication), CWE-1188 (Insecure Default
Initialization of Resource).

## Usage

```
python3 detect.py <file-or-dir> [more...]
```

Exit codes: `0` clean, `1` findings, `2` usage error.

```
$ python3 detect.py examples/bad/
examples/bad/01_no_auth_block.yml:1: docker registry config has no top-level `auth:` block ...
examples/bad/02_empty_auth_map.yml:7: docker registry `auth:` block is empty ...
examples/bad/03_silly_auth.yml:7: docker registry uses `auth.silly` ...
examples/bad/04_compose_no_auth_env.yml:3: docker-compose service `registry` runs registry:2 image ...
```

## Verify

```
./smoke.sh    # bad=4/4 good=0/4 PASS
```

## Limitations

- Heuristic, not a YAML parser; uses indentation-based key walking
  (sufficient for `config.yml` and `docker-compose.yml` shapes seen
  in the wild).
- Will not detect external bearer tokens delivered by a sidecar
  reverse proxy if the registry config itself has no `auth:` --
  this is correct: the registry is still wide open if the proxy is
  bypassed (host network, internal cluster traffic).
- Stdlib-only, no third-party dependencies.
