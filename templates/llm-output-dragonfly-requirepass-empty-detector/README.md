# llm-output-dragonfly-requirepass-empty-detector

Stdlib-only Python detector that flags **DragonflyDB** (the in-memory,
Redis-protocol-compatible datastore from dragonflydb.io) deployments
that are started **without a `--requirepass` value**, leaving the
data plane open to anyone who can reach port 6379.

Maps to **CWE-306** (Missing Authentication for Critical Function),
**CWE-1188** (Insecure Default Initialization), **CWE-862** (Missing
Authorization), OWASP **A05:2021 Security Misconfiguration**.

## Why this is a problem

Dragonfly speaks the Redis wire protocol. By default, with no
`--requirepass` set, every connecting client gets full RW access:
`FLUSHALL`, `KEYS *`, `SET`, `DEBUG SLEEP`, `MEMORY USAGE`, every
admin command. The official Dragonfly docs say it explicitly:

> "If `--requirepass` is not set, the server accepts unauthenticated
>  connections."
> -- https://www.dragonflydb.io/docs/managing-dragonfly/authentication

Because Dragonfly's quickstart docker-compose example is literally:

```yaml
services:
  dragonfly:
    image: docker.dragonflydb.io/dragonflydb/dragonfly
    ports: ["6379:6379"]
```

— with no `requirepass` — every "self-hosted Dragonfly" tutorial
copies the same shape, and LLMs reproduce it verbatim into manifests
that are then exposed via NodePorts, ingress controllers, or just
`0.0.0.0:6379`.

Internet-exposed unauthenticated Dragonfly has shown the same
ransom-note pattern as historical unauthenticated Redis.

## Why LLMs ship this

Every Dragonfly quickstart, blog post, and `docker run` snippet
omits `--requirepass`, because the docs want you to be running in
two seconds. The model copies the demo shape into a "production"
manifest without re-adding the auth flag.

## Heuristic

We look for Dragonfly invocations and flag them when **no
`--requirepass=<non-empty, non-trivial>`** is present.

We flag:

1. **CLI / shell / Dockerfile `CMD` / docker-compose `command:` /
   k8s `args:` / systemd `ExecStart=`** that runs `dragonfly`
   binary or pulls the `dragonflydb/dragonfly` image, with no
   `--requirepass` flag at all.
2. Explicit empty values: `--requirepass=`, `--requirepass ""`.
3. Weak placeholder values: `admin`, `password`, `dragonfly`,
   `changeme`, etc., or anything shorter than 12 chars.

We do NOT flag:

- Vanilla Redis (`redis-server`, `image: redis:*`) — covered by a
  separate detector in this chain.
- Documentation / comments that mention Dragonfly without an actual
  invocation.
- Dragonfly invocations with `--requirepass=<>=12 chars, not on the
  weak list>`.

## Usage

```sh
python3 detect.py path/to/file_or_dir [more...]
```

Exit codes: `0` clean, `1` findings, `2` usage error.

## Worked example

```sh
$ cd templates/llm-output-dragonfly-requirepass-empty-detector
$ ./smoke.sh
bad=4/4 good=0/4
PASS
```

## Fixtures

`examples/bad/` — 4 samples that should all flag:

- `01_compose_no_pass.yaml` — quickstart docker-compose with no
  `--requirepass`.
- `02_dockerfile_cmd.Dockerfile` — Dockerfile CMD invokes dragonfly
  on `0.0.0.0:6379` without auth.
- `03_systemd_empty_pass.service` — systemd unit with
  `--requirepass=` (empty).
- `04_k8s_weak_pass.yaml` — k8s Deployment with
  `--requirepass=admin`.

`examples/good/` — 4 samples that should not flag:

- `01_compose_strong_pass.yaml` — strong pass + loopback bind.
- `02_dockerfile_strong.Dockerfile` — strong pass via JSON-array CMD.
- `03_systemd_strong.service` — strong pass via env var expansion.
- `04_doc_only.conf` — comments only, no actual invocation.

## Suggested remediation

```yaml
services:
  dragonfly:
    image: docker.dragonflydb.io/dragonflydb/dragonfly:latest
    command:
      - "dragonfly"
      - "--requirepass=${DRAGONFLY_REQUIREPASS}"   # >= 32 random chars
    ports:
      - "127.0.0.1:6379:6379"   # loopback unless behind mTLS proxy
    environment:
      DRAGONFLY_REQUIREPASS_FILE: /run/secrets/dragonfly_pass
    secrets:
      - dragonfly_pass
```

Pair with: bind to loopback (or a private overlay), front with
stunnel / a TLS proxy if you must expose it, and rotate the secret
on a schedule.
