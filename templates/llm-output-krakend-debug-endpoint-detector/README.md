# llm-output-krakend-debug-endpoint-detector

Stdlib-only Python detector that flags **KrakenD** API gateway
configurations that enable the top-level `debug_endpoint` and/or
`echo_endpoint` flags (or their `--debug` / `--echo` CLI / env-var
equivalents). Maps to **CWE-489** (active debug code), **CWE-200**
(exposure of sensitive information), and **CWE-215** (insertion of
sensitive information into debugging code).

KrakenD's `/__debug/<path>` echoes the full incoming request --
including the `Authorization` header, cookies, and any internal
routing headers injected by upstream auth proxies. `/__echo/<path>`
additionally reflects the backend response, making it a one-stop
shop for SSRF confirmation and token harvesting. KrakenD docs
explicitly say "never enable these in production".

LLMs ship this misconfig because the upstream `Hello World` JSON
snippets enable both flags for the walk-through and most blog posts
copy them verbatim into `krakend.json`.

## Heuristic

We look for any of:

1. **JSON / JSONC**: a top-level `"debug_endpoint": true` or
   `"echo_endpoint": true`.
2. **YAML**: the same keys with value `true` / `yes` / `on`.
3. **CLI / Dockerfile**: `krakend run` or `krakend check` invocations
   with the `-d` / `--debug` / `-e` / `--echo` flag.
4. **Env vars**: `KRAKEND_DEBUG_ENDPOINT=true` /
   `KRAKEND_ECHO_ENDPOINT=true`.

Comments (`#`, `//`, `/* ... */`) are stripped before matching so
that a disabled-for-production example with a `# debug_endpoint:
true` comment does not fire.

## CWE / standards

- **CWE-489**: Active Debug Code.
- **CWE-200**: Exposure of Sensitive Information to an Unauthorized
  Actor.
- **CWE-215**: Insertion of Sensitive Information Into Debugging Code.
- KrakenD docs: "The debug and echo endpoints must NEVER be enabled
  in a production environment."

## What we accept (no false positive)

- `"debug_endpoint": false` / `"echo_endpoint": false`.
- The keys absent entirely (default is `false`).
- A `# debug_endpoint: true` line in YAML / a `// "debug_endpoint":
  true` line in JSONC (both treated as commented-out).
- `krakend run` with no `-d` / `-e` flags.

## What we flag

- `krakend.json` with `"debug_endpoint": true`.
- `krakend.yaml` with `echo_endpoint: yes`.
- `Dockerfile` `CMD ["krakend", "run", "-c", "/etc/krakend/krakend.json", "-d"]`.
- `.env` file with `KRAKEND_ECHO_ENDPOINT=true`.

## Limits / known false negatives

- We don't inspect per-endpoint debug toggles inside the `endpoints`
  array (e.g. a `proxy` middleware with `debug: true`). That's a
  separate detector class.
- We don't check for non-default `debug_pattern` (used to namespace
  the debug path); even a renamed debug endpoint is still a leak.
- A `flexible_config` template that renders to `true` at runtime via
  an env-var substitution we don't evaluate will be missed.

## Usage

```bash
python3 detect.py path/to/krakend.json
python3 detect.py path/to/repo/
```

Exit codes: `0` = no findings, `1` = findings (printed to stdout),
`2` = usage error.

## Smoke test

```
$ bash smoke.sh
bad=4/4 good=0/4
PASS
```

Layout:

```
examples/bad/
  01_krakend.json               # "debug_endpoint": true at top level
  02_krakend.yaml               # echo_endpoint: yes
  03_dockerfile.Dockerfile      # CMD krakend run --debug
  04_compose.env-example        # KRAKEND_DEBUG_ENDPOINT=true
examples/good/
  01_krakend.json               # both flags false
  02_commented.yaml             # `# debug_endpoint: true` (commented)
  03_dockerfile.Dockerfile      # plain `krakend run -c krakend.json`
  04_compose.env-example        # KRAKEND_DEBUG_ENDPOINT=false
```
