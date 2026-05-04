# llm-output-uwsgi-stats-server-public-bind-detector

Detects uWSGI configurations that enable the **stats server** on a
non-loopback bind address (or a bare port, which means "all
interfaces").

## What it flags

The `stats` / `stats-server` / `stats_server` option in:

- INI / conf files (in or outside an explicit `[uwsgi]` section)
- YAML files (top-level or under `uwsgi:`)
- CLI flag forms in shell scripts, Dockerfiles, systemd units,
  docker-compose `command:` entries

Public bind heuristics: bare `:port`, `0.0.0.0:port`, `*:port`,
`[::]:port`, `::port`, or any non-loopback IP/hostname before the
port.

Loopback (`127.0.0.1`, `::1`, `localhost`) and any unix-socket form
(`/path`, `unix:/path`, `*.sock`) are NOT flagged.

## Why it matters

The uWSGI stats server is a JSON endpoint exposing every worker's:

- pid, status, request count, exception count
- **the full URI of the request currently being processed**
- memory (rss / vsz), CPU times
- mounted apps and plugins
- core, signal-queue, lock and cache state

There is no auth; there is no TLS. The official docs say:
*"do not expose the stats server to the public, it contains
sensitive data."* Most copy-pasteable monitoring snippets ignore
that line. CWE-200 / CWE-419 / CWE-668.

## Usage

```
python3 detect.py <file-or-dir> [more...]
```

Exit codes: `0` clean, `1` findings, `2` usage error.

```
$ python3 detect.py examples/bad/
examples/bad/01_bare_port.ini:6: uwsgi `stats = :1717` -> bare port (binds all interfaces); ...
examples/bad/02_zeros.ini:7: uwsgi `stats = 0.0.0.0:9191` -> 0.0.0.0 (all IPv4 interfaces); ...
examples/bad/03_yaml_wildcard.yaml:6: uwsgi yaml `stats: *:1717` -> wildcard host *; ...
examples/bad/04_cli_flag.sh:8: uwsgi CLI --stats 0.0.0.0:1717 -> ...
```

## Verify

```
./smoke.sh    # bad=4/4 good=0/4 PASS
```

## Limitations

- Stdlib only; INI parsing is line-oriented (sufficient for uWSGI).
- YAML scanner is indent-aware but does not implement the full YAML
  spec; flow-style `{stats: ":1717"}` mappings are not handled.
- A `stats = $STATS_BIND` form referencing an env var is treated as
  "unrecognised value" and not flagged -- by design, we do not
  follow shell expansion.
