# llm-output-rethinkdb-bind-no-http-auth-detector

Stdlib-only Python detector that flags **RethinkDB** server
configurations and invocations which expose the cluster / driver /
HTTP-admin endpoints to all interfaces with **no admin password set**.

RethinkDB ships with an empty `admin` password by default, and the
web admin UI on port 8080 has no separate authentication layer —
anyone who can reach the HTTP listener can run arbitrary ReQL,
including `r.db("rethinkdb").table("users").get("admin").update(...)`.
The recommended hardening is either to keep `--bind` on `127.0.0.1`
**or** to set an admin password via `--initial-password`.

Maps to:
- **CWE-306**: Missing Authentication for Critical Function.
- **CWE-1188**: Insecure Default Initialization of Resource.
- **CWE-668**: Exposure of Resource to Wrong Sphere.

## Heuristic

We flag any of the following, outside `#` / `;` comment lines:

1. `--bind all` (or `bind=all`, or `bind: all`) on a `rethinkdb`
   command line / Dockerfile / compose / systemd unit / k8s args
   list, when the same file does **not** also set
   `--initial-password ...` (a non-empty value, not `auto`).
2. `bind=all` in a `rethinkdb.conf` style config when no
   `initial-password=...` line is present.
3. Exec-array form: `["rethinkdb", ..., "--bind", "all", ...]` in
   k8s container args / docker-compose command arrays (handled
   across two list elements).
4. Explicit `--initial-password ""` (empty) or `initial-password=`
   (empty) — that is the documented "auth disabled" form.

Each occurrence emits one finding line.

## CWE / standards

- **CWE-306**: Missing Authentication for Critical Function.
- **CWE-1188**: Insecure Default Initialization of Resource.
- **CWE-668**: Exposure of Resource to Wrong Sphere.
- RethinkDB `rethinkdb` man page, `--bind`: "Add an address to bind
  to. Use `all` to bind to all local addresses. **The default is to
  bind only to local addresses.**"
- RethinkDB security guide: "If you must expose RethinkDB on a
  public interface, set `--initial-password` to a non-empty value
  on first start; otherwise the `admin` user has an empty password
  and the HTTP admin UI on 8080 grants full ReQL execution."

## What we accept (no false positive)

- `--bind 127.0.0.1` (the secure default).
- `--bind all --initial-password s3cret` (auth set, exposure
  intentional).
- `bind=127.0.0.1` in `rethinkdb.conf`.
- Documentation / commented-out lines (`# --bind all`).
- The string `bind` in unrelated contexts (e.g. `bind-mount`,
  `bind9`, a comment about address binding).

## Layout

```
detect.py            stdlib-only scanner (regex over text)
smoke.sh             runs detect.py against examples/ and asserts
examples/bad/        4 fixtures that MUST be flagged
examples/good/       3 fixtures that MUST NOT be flagged
```

## Run

```
python3 detect.py path/to/rethinkdb.conf
python3 detect.py path/to/repo
bash smoke.sh
```

Exit codes: `0` = clean, `1` = findings, `2` = usage error.

## Why this is a real LLM failure mode

Every "RethinkDB on Docker" or "RethinkDB on a single VPS"
tutorial reaches for `--bind all` to make the web admin reachable
from the developer's laptop, and almost none of them set
`--initial-password`. LLMs asked "I cannot reach the RethinkDB
admin UI from outside the host" reliably answer with `--bind all`
and forget the matching `--initial-password`. The detector exists
to catch the paste before it reaches a Compose file, a Helm chart,
or a systemd unit on a public-IP node.
