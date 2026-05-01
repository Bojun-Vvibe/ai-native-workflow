# llm-output-dockerfile-root-user-detector

Single-pass python3 stdlib scanner for Dockerfiles whose final image
runs as root. Flags `USER root` / `USER 0` / `USER 0:0` in the final
build stage, and any final stage with no `USER` directive at all
(which defaults to root).

## Why it exists

A container whose entrypoint runs as uid 0 is "just root inside the
container", but combined with common operational patterns — bind-mounted
host paths, shared kernels, missing `no-new-privileges`, capability
defaults, mounted docker sockets — root in the container widens the
blast radius of any RCE in the workload to the host's docker group,
which is effectively root on the host.

LLMs love to emit Dockerfiles that copy code, `RUN pip install`, and
go straight to `CMD ["python", "app.py"]` with no `USER` directive.
The same pattern shows up when an early `USER nonroot` is overridden
by a later `USER root` for a `RUN apt-get install` step but the author
forgets to drop again before `CMD`.

## What it flags

In `Dockerfile`, `Dockerfile.*`, `*.Dockerfile`, `*.dockerfile`,
`Containerfile`, `Containerfile.*`:

- `USER root` (case-insensitive) in the **final** build stage —
  emitted as `dockerfile-user-root-explicit`.
- `USER 0` / `USER 0:0` / `USER 0:<group>` / `USER root:<group>` in
  the final stage — same kind.
- A final stage with no `USER` directive at all — emitted once per
  file as `dockerfile-no-user`.
- The "effective final user is root" condition — when the LAST
  `USER` directive in the final stage resolves to root — emitted as
  `dockerfile-final-user-root`.

## What it does NOT flag

- Dockerfiles whose final `USER` is a non-root name or non-zero uid.
- `USER root` in an intermediate `FROM ... AS build` stage when the
  final stage drops to a non-root user. Multi-stage builds are
  evaluated per-stage; only the last stage is the one that ships.
- Lines marked with a trailing `# docker-root-ok` comment.
- `USER root` appearing inside a `# ...` comment line.

## Usage

```bash
python3 detect.py path/to/file_or_dir [more paths ...]
```

Exit code:

- `0` — no findings
- `1` — at least one finding
- `2` — usage error

## Worked example

`examples/bad/` has 4 dangerous Dockerfiles that produce 7 findings;
`examples/good/` has 2 safe Dockerfiles that produce 0 findings.

```
$ ./verify.sh
bad findings:  7 (rc=1)
good findings: 0 (rc=0)
PASS
```

Verbatim scanner output on `examples/bad/`:

```
examples/bad/Dockerfile:7:1: dockerfile-user-root-explicit — USER root
examples/bad/Dockerfile:7:1: dockerfile-final-user-root — final USER is 'root'
examples/bad/Dockerfile.nouser:2:1: dockerfile-no-user — final stage has no USER directive
examples/bad/Dockerfile.reelevate:12:1: dockerfile-user-root-explicit — USER root
examples/bad/Dockerfile.reelevate:12:1: dockerfile-final-user-root — final USER is 'root'
examples/bad/Dockerfile.uid0:4:1: dockerfile-user-root-explicit — USER 0
examples/bad/Dockerfile.uid0:4:1: dockerfile-final-user-root — final USER is '0'
# 7 finding(s)
```

## Suppression

Add `# docker-root-ok` at the end of any line you have audited (e.g.
a base image whose entrypoint script `gosu`s down to a non-root user
at runtime).

## Layout

```
llm-output-dockerfile-root-user-detector/
├── README.md
├── detect.py
├── verify.sh
└── examples/
    ├── bad/
    │   ├── Dockerfile
    │   ├── Dockerfile.nouser
    │   ├── Dockerfile.reelevate
    │   └── Dockerfile.uid0
    └── good/
        ├── Dockerfile
        └── Dockerfile.multistage
```

## Limitations

- Single-line analysis. A `USER` directive split across lines via
  backslash continuation is not reassembled.
- No build-arg resolution. `USER ${APP_USER}` is treated as a
  non-root token regardless of default value.
- `ARG`/`ENV` substitution is not performed; if the only `USER`
  directive is `USER ${ROOT_USER:-root}` the detector trusts the
  literal `${ROOT_USER:-root}` is non-root.
- Entrypoint scripts that re-elevate at runtime (`sudo`, `gosu`,
  `setpriv`) are not analysed; they are out of scope.
