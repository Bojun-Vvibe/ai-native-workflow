# llm-output-docker-compose-privileged-true-detector

Static lint that flags docker-compose YAML files which grant a
service host-level (or near-host-level) privileges via any of:

- `privileged: true`
- `cap_add: [ALL]` / `[SYS_ADMIN]` / `[SYS_PTRACE]` / `[SYS_MODULE]`
  / `[DAC_READ_SEARCH]` / `[NET_ADMIN]`
- `security_opt: [seccomp:unconfined]` /
  `[apparmor:unconfined]` / `[no-new-privileges:false]`
- `pid: host`
- `ipc: host`
- `network_mode: host`
- `userns_mode: host`

## Why LLMs emit this

`privileged: true` in a Compose service is the docker-compose
equivalent of `docker run --privileged` — the container gets ~all
kernel capabilities, all device nodes, and (depending on the
runtime) effectively becomes a thin wrapper around the host kernel.
A compromise of any process inside such a container is
indistinguishable from a compromise of the host.

Each of the other patterns above achieves a similar escape vector
by a different route (capability grant, kernel filter bypass, or
namespace sharing).

LLMs emit these patterns frequently because the most common
StackOverflow answer for "docker container can't access /dev/...",
"my container can't ping", or "FUSE doesn't work in docker" is
"add `privileged: true`" — without any qualification that this is
appropriate only for short-lived debugging.

## What it catches

Per-service, per-key findings — one per offending key. The detector
walks the YAML structurally so commented lines are ignored and each
finding is attributed to the exact `file:line`.

## What it does NOT flag

- `privileged: false` (or any falsy form)
- `cap_add` lists that contain only safe capabilities (e.g.
  `NET_BIND_SERVICE`)
- Files that are not docker-compose YAML (no top-level `services:`
  key)
- Lines with a trailing `# compose-priv-ok` comment
- Files containing `compose-priv-ok-file` anywhere

## How to detect

```sh
python3 detector.py path/to/compose-dir/
```

Exit code = number of files with a finding (capped 255). Stdout:
`<file>:<line>:<reason>`.

## Safe pattern

```yaml
version: "3.9"
services:
  hardened:
    image: ghcr.io/example/hardened:2.0.0
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
    security_opt:
      - "no-new-privileges:true"
    read_only: true
    tmpfs:
      - /tmp
```

## Refs

- CWE-250: Execution with Unnecessary Privileges
- CWE-269: Improper Privilege Management
- docker docs: Compose file reference (`privileged`, `cap_add`,
  `security_opt`, `pid`, `ipc`, `network_mode`, `userns_mode`)
- CIS Docker Benchmark §5.4 — Ensure that privileged containers
  are not used

## Verify

```sh
bash verify.sh
```

Should print `bad=4/4 good=0/3 PASS`.
