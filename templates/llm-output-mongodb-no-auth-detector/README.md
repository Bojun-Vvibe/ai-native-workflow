# llm-output-mongodb-no-auth-detector

Single-pass python3 stdlib scanner for MongoDB shipped without
authentication. Flags `mongod.conf` with `security.authorization:
disabled` (or no `security:` block at all), `mongod --noauth` /
bare `mongod` invocations missing `--auth`, and `docker-compose`
mongo services with neither `MONGO_INITDB_ROOT_*` env nor an
`--auth` flag.

## Why it exists

A `mongod` process started without authentication accepts every
client on every reachable interface as a fully-privileged user. The
historical default was "auth off + bind 127.0.0.1", and the
docker-compose / kubernetes / helm shapes LLMs emit routinely flip
the bind to `0.0.0.0` while leaving auth off, producing the
canonical "publicly reachable, unauthenticated MongoDB" that has
been mass-scanned and ransomed since at least 2017.

LLMs love the minimal `mongo` quick-start: pull the image, expose
port 27017, no env, no creds, no `command:` override. The same
shape leaks into Helm `values.yaml`, into Dockerfile `CMD
["mongod"]`, and into bash entrypoints that pass `--bind_ip
0.0.0.0` without `--auth`.

## What it flags

In `mongod.conf` / `mongod*.yaml` / `mongod*.yml`:

- `security.authorization: disabled` (any quoting, case-insensitive)
  → `mongodb-config-authorization-disabled`.
- A `net:` block present but no `security:` block at all → reported
  once per file as `mongodb-config-no-security-block`.

In `Dockerfile*`, `*.Dockerfile`, `*.sh`, `*.bash`:

- `mongod ... --noauth` → `mongodb-cli-noauth-flag`.
- A bare `mongod ...` invocation with neither `--auth` nor
  `--keyFile` → `mongodb-cli-no-auth-flag`. Lines that look like
  package-management or filesystem helpers (apt, yum, mkdir, chown,
  …) are skipped. Lines that load a config via `--config` are
  trusted to be covered by the YAML scan.

In `docker-compose*.yml` / `compose*.yml`:

- A service whose `image:` starts with `mongo` / `mongod` and which
  has neither `MONGO_INITDB_ROOT_USERNAME` + `MONGO_INITDB_ROOT_PASSWORD`
  nor `--auth` / `--keyFile` in any `command:` → reported as
  `mongodb-compose-no-root-creds`.
- Same service with explicit `--noauth` in `command:` →
  `mongodb-compose-noauth-flag`.

## What it does NOT flag

- mongod configs with `security.authorization: enabled`.
- Shell / CMD lines that include `--auth` or `--keyFile`.
- Lines marked with a trailing `# mongo-noauth-ok` comment.
- Service blocks where any line carries `# mongo-noauth-ok`.
- Patterns inside `#` comment lines.

## Usage

```bash
python3 detect.py path/to/file_or_dir [more paths ...]
```

Exit code:

- `0` — no findings
- `1` — at least one finding
- `2` — usage error

## Worked example

`examples/bad/` has 4 dangerous artefacts producing 5 findings;
`examples/good/` has 3 safe artefacts producing 0 findings.

```
$ ./verify.sh
bad findings:  5 (rc=1)
good findings: 0 (rc=0)
PASS
```

Verbatim scanner output on `examples/bad/`:

```
examples/bad/docker-compose.yml:4:1: mongodb-compose-no-root-creds — service 'db' mongo image without ROOT creds and no --auth
examples/bad/mongod-nosec.yaml:1:1: mongodb-config-no-security-block — mongod-style config has net: block but no security: block
examples/bad/mongod.conf:8:1: mongodb-config-authorization-disabled — authorization: disabled
examples/bad/start.sh:5:1: mongodb-cli-noauth-flag — mongod --dbpath /data/db --bind_ip 0.0.0.0 --noauth &
examples/bad/start.sh:6:1: mongodb-cli-no-auth-flag — mongod --dbpath /data/db2 --bind_ip 0.0.0.0 --port 27018 &
# 5 finding(s)
```

## Suppression

Add `# mongo-noauth-ok` at the end of any line you have audited
(e.g. a `mongod` invoked inside a unit test fixture bound to
127.0.0.1 only). For docker-compose service blocks, place the
suppression comment on any line within the service.

## Layout

```
llm-output-mongodb-no-auth-detector/
├── README.md
├── detect.py
├── verify.sh
└── examples/
    ├── bad/
    │   ├── docker-compose.yml
    │   ├── mongod-nosec.yaml
    │   ├── mongod.conf
    │   └── start.sh
    └── good/
        ├── docker-compose.yml
        ├── mongod.conf
        └── start.sh
```

## Limitations

- YAML parsing is line-oriented; deeply nested or multi-document
  YAML files may not be classified correctly. The scanner trusts
  top-level indentation under `services:` to be exactly 2 spaces.
- Helm / Kubernetes manifests are not first-class — only the
  docker-compose shape is recognised. Pipe a rendered manifest
  through if you need k8s coverage.
- `MONGO_INITDB_ROOT_PASSWORD_FILE` is treated as satisfying the
  password-set requirement only when the literal env key
  `MONGO_INITDB_ROOT_PASSWORD` also appears in the same service
  block (a deliberate choice — secrets-via-file should still be
  paired with the explicit env name in the manifest for clarity).
- No analysis of `--keyFile` validity, x509 mode, LDAP auth, or
  Atlas-managed clusters; auth-on at the wire is the only thing
  this checks.
