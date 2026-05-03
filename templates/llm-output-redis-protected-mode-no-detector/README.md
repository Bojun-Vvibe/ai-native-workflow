# llm-output-redis-protected-mode-no-detector

Stdlib-only Python detector that flags **Redis** configurations which
disable `protected-mode`. Maps to **CWE-306** (missing authentication
for critical function), **CWE-1188** (insecure default initialization
of resource), and **CWE-284** (improper access control).

Redis ships with `protected-mode yes` since 3.2.0 specifically because
huge numbers of internet-exposed, unauthenticated Redis instances were
being trivially RCE'd via `CONFIG SET dir` + `SAVE` writing to
`~/.ssh/authorized_keys` or to a webroot. Protected mode is the safety
net that refuses non-loopback connections when no auth is configured.

When an LLM (or a copy-pasted "Redis won't connect from another box"
Stack Overflow answer) sets `protected-mode no`, the safety net is
gone. Any network reachability + missing `requirepass` = full RCE.

## Heuristic

We flag any of the following, outside `#` comment lines:

1. `protected-mode no` directive in `redis.conf`-style files.
2. `--protected-mode no` (or `=no`) on a `redis-server` command line.
3. `CONFIG SET protected-mode no` issued at runtime (case-insensitive).
4. Exec-array form: `["redis-server", ..., "--protected-mode", "no"]`
   (k8s args / docker-compose `command:` arrays).

Each occurrence emits one finding line.

## CWE / standards

- **CWE-306**: Missing Authentication for Critical Function.
- **CWE-1188**: Insecure Default Initialization of Resource.
- **CWE-284**: Improper Access Control.
- Redis docs: "By default protected-mode is enabled. You should disable
  it only if you are sure you want clients from other hosts to connect
  to Redis even if no authentication is configured."

## What we accept (no false positive)

- `protected-mode yes` (the safe default).
- Bound to a single non-loopback interface *with* `requirepass` set.
- Documentation / commented-out lines (`# protected-mode no`).
- HCL / YAML keys that happen to share the prefix (e.g. `protected_mode_status`).

## Layout

```
detect.py            stdlib-only scanner (regex over text)
smoke.sh             runs detect.py against examples/ and asserts
examples/bad/        ≥3 fixtures that MUST be flagged
examples/good/       ≥3 fixtures that MUST NOT be flagged
```

## Run

```
python3 detect.py path/to/redis.conf
python3 detect.py path/to/repo
bash smoke.sh
```

Exit codes: `0` = clean, `1` = findings, `2` = usage error.

## Why this is a real LLM failure mode

`protected-mode no` is the single most common "fix" suggested when a
developer hits `DENIED Redis is running in protected mode` in a dev
container. The LLM helpfully suggests it, the developer pastes it into
their docker-compose, and the same compose file gets reused in prod
with a `0.0.0.0` bind. The detector exists to catch the paste before
it ships.
