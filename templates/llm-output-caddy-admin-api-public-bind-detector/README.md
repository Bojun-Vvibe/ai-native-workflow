# llm-output-caddy-admin-api-public-bind-detector

Stdlib-only Python detector that flags **Caddy** server configurations
that expose the admin API on a non-loopback address. Maps to
**CWE-306** (missing authentication for critical function),
**CWE-668** (exposure of resource to wrong sphere), and **CWE-1188**
(insecure default initialization).

Caddy's admin API:

- listens on `localhost:2019` by default,
- is **completely unauthenticated**,
- can load arbitrary configuration: new sites, reverse-proxy
  upstreams, TLS keys, exec'd handlers,
- is documented as "intended for use only by trusted clients on the
  same machine".

When that endpoint is bound to `0.0.0.0`, `:2019`, `[::]`, or any
other non-loopback address (typical in Docker tutorials), full
server takeover is one `curl` away.

## Heuristic

Outside `#` / `//` comments, we flag:

1. Caddyfile global block: `admin <host>:<port>` where `<host>` is
   not `localhost`, `127.0.0.1`, `[::1]`, `::1`, or a `unix/...`
   socket. `admin off` is intentionally ignored (that disables the
   API entirely, which is safe).
2. JSON config: `"admin": { "listen": "<host>:<port>" }` with a
   non-loopback host.
3. CLI: a `caddy ...` invocation with `--address <host>:<port>` (or
   `-address`) where the line also references `admin`.
4. Env var `CADDY_ADMIN=<host>:<port>` with a non-loopback host.

`admin :2019` (empty host) is treated as non-loopback because Caddy
binds it to all interfaces.

## Files scanned

- `Caddyfile`, `*.caddyfile`
- `*.json`, `*.yaml`, `*.yml`, `*.conf`
- `Dockerfile`, `*.sh`, `*.bash`, `*.service`

## Usage

```sh
python3 detect.py path/to/Caddyfile
python3 detect.py path/to/dir/
```

Exit codes: `0` = no findings, `1` = findings, `2` = usage error.

## Smoke

```sh
./smoke.sh
```

Expects `bad=6/6 good=6/6` (all bad fixtures flagged, no false
positives on good fixtures).
