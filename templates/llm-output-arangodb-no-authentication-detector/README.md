# llm-output-arangodb-no-authentication-detector

Stdlib-only Python detector that flags **ArangoDB** server
configurations and invocations which disable authentication —
i.e. `--server.authentication false` on the `arangod` command
line, `authentication = false` under `[server]` in `arangod.conf`,
or `ARANGO_NO_AUTH=1` env override on the official Docker image
(which makes the entrypoint start the server with auth disabled
and a NULL `root` password accessible from any client that can
reach the listener).

Maps to:
- **CWE-306**: Missing Authentication for Critical Function.
- **CWE-1188**: Insecure Default Initialization of Resource.
- **CWE-732**: Incorrect Permission Assignment for Critical Resource.

The ArangoDB docs are explicit: "Disable authentication only for
**throwaway** development setups. With authentication off, anyone
who can reach the coordinator's HTTP/HTTPS listener (default
8529) can read, modify, and drop every database." Yet
`--server.authentication false` and `ARANGO_NO_AUTH=1` are the
single most common copy-paste from the official "Quickstart"
container instructions and from blog posts that want to sidestep
the JWT-secret bootstrap dance.

## Heuristic

We flag any of the following, outside `#` comment lines:

1. `--server.authentication false` (or `=false`, or `0`, or `no`,
   or `off`) on a shell command line, a Dockerfile CMD/ENTRYPOINT,
   a systemd `ExecStart`, a docker-compose `command:` line, or a
   k8s container args list.
2. `authentication = false` (or `: false`) under a `[server]`
   block in an `arangod.conf` (we tolerate any whitespace and any
   case).
3. `ARANGO_NO_AUTH=1` (or `=true`, `=yes`) env override — used by
   the official `arangodb/arangodb` image entrypoint to start the
   server with authentication disabled.
4. Exec-array form: `["arangod", ..., "--server.authentication",
   "false", ...]` in k8s container args / docker-compose command
   arrays (handled across two list elements).

Each occurrence emits one finding line.

## CWE / standards

- **CWE-306**: Missing Authentication for Critical Function.
- **CWE-1188**: Insecure Default Initialization of Resource.
- **CWE-732**: Incorrect Permission Assignment for Critical Resource.
- ArangoDB `arangod` man page, `--server.authentication`:
  "Setting this to `false` disables authentication on the server
  and allows arbitrary clients to access the database **with
  full administrative privileges**."

## What we accept (no false positive)

- `--server.authentication true` (the secure default).
- `authentication = true` under `[server]`.
- `ARANGO_ROOT_PASSWORD=...` (the recommended bootstrap path).
- Documentation / commented-out lines (`# --server.authentication false`).
- The string `authentication` in unrelated contexts (e.g. a
  comment about LDAP authentication, a variable name like
  `enable_ldap_authentication = true`).

## Layout

```
detect.py            stdlib-only scanner (regex over text)
smoke.sh             runs detect.py against examples/ and asserts
examples/bad/        4 fixtures that MUST be flagged
examples/good/       3 fixtures that MUST NOT be flagged
```

## Run

```
python3 detect.py path/to/arangod.conf
python3 detect.py path/to/repo
bash smoke.sh
```

Exit codes: `0` = clean, `1` = findings, `2` = usage error.

## Why this is a real LLM failure mode

The ArangoDB Docker quickstart shows `-e ARANGO_NO_AUTH=1` as a
"just get it running" shortcut. Every "deploy ArangoDB on
Kubernetes" tutorial that predates the operator-managed JWT
secret reuses `--server.authentication false` to skip the cert /
JWT bootstrap. LLMs asked "why is my ArangoDB pod CrashLoopBackOff
with `please set ARANGO_ROOT_PASSWORD`" reliably suggest
`ARANGO_NO_AUTH=1`, which "fixes" the crash by making the cluster
world-readable on port 8529. The detector exists to catch the
paste before it reaches a Helm chart, an Argo CD application, or a
GitOps-tracked manifest.
