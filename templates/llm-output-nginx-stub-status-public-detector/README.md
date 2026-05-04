# llm-output-nginx-stub-status-public-detector

Stdlib-only Python detector that flags nginx `location` blocks
which enable `stub_status` (the `ngx_http_stub_status_module`
endpoint) without restricting access via `allow`/`deny` ACLs,
`auth_basic`, `auth_request`, or `internal;`. Maps to **CWE-200**,
**CWE-419**, **CWE-668**, OWASP **A01:2021 Broken Access Control**.

## What it catches

The `stub_status` endpoint exposes active connections, total
accepted / handled / requests counters, and reading / writing /
waiting state counts. When reachable from the public internet it
leaks operational telemetry useful for capacity-planning attacks,
side-channel inference, and target recon.

The official nginx docs and most "nginx + prometheus-nginx-exporter"
tutorials show:

```
location /nginx_status {
    stub_status;
}
```

with no `allow 127.0.0.1; deny all;` and no `auth_basic`. LLMs
copy the snippet verbatim into reverse-proxy configs that ship to
production on `:80` / `:443`.

## Heuristic

For each `location ... { ... }` block whose body contains
`stub_status;`, require at least one guard inside the same block:

- `deny all;`
- `auth_basic "<realm>";`  (but not `auth_basic off;`)
- `auth_request <uri>;`
- `internal;`

Always flag explicit anti-patterns inside the same block:

- `allow all;`
- `allow 0.0.0.0/0;`
- `allow ::/0;`

Comments (`# ...`) are stripped before parsing, so commented-out
directives do not count as guards and do not falsely accuse.

## Worked example

```
$ bash smoke.sh
bad=4/4 good=0/4
PASS
```

## Layout

```
examples/bad/
  01_naked_stub_status.conf       # location /nginx_status { stub_status; } only
  02_allow_all.conf               # stub_status; allow all;
  03_allow_zero_cidr.conf         # stub_status; allow 0.0.0.0/0;
  04_auth_basic_off.conf          # stub_status; auth_basic off;
examples/good/
  01_loopback_allow_deny.conf     # allow 127.0.0.1; deny all; stub_status;
  02_auth_basic.conf              # stub_status; auth_basic "metrics";
  03_internal_only.conf           # stub_status; internal;
  04_commented_only.conf          # stub_status only inside `# ...` comment
```

## Usage

```bash
python3 detect.py path/to/nginx.conf
python3 detect.py path/to/conf.d/
```

Exit codes: `0` = clean, `1` = findings (printed to stdout), `2` =
usage error.

## Limits

- Access control inherited from a wrapping `if` block is not
  considered a guard.
- mTLS enforced at the parent `server` level
  (`ssl_verify_client on;`) is not climbed; only the same
  `location` block is inspected.
- Templated configs (Jinja, Sprig, ERB) are not rendered;
  values that resolve to a guard only after rendering are
  out of scope.
