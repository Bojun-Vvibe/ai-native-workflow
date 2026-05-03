# llm-output-oauth2-proxy-skip-auth-regex-permissive-detector

Stdlib-only Python detector that flags **`oauth2-proxy`** deployments
configured with a permissive `--skip-auth-regex` /
`--skip-auth-route` / `skip_auth_regex` / `skip_auth_routes` value
that effectively disables authentication for the upstream.

Maps to **CWE-284** (improper access control), **CWE-287** (improper
authentication), and **CWE-697** (incorrect comparison — overly broad
regex).

## Why this matters

`oauth2-proxy` (https://github.com/oauth2-proxy/oauth2-proxy) sits
in front of an upstream and forces an OIDC / OAuth2 round-trip.
Each value passed to `--skip-auth-regex` (deprecated alias of
`--skip-auth-route`) is a Go regexp; if the request path matches,
the request is forwarded to the upstream **with no authentication**.

LLMs frequently emit:

```bash
oauth2-proxy --skip-auth-regex='^.*$'
oauth2-proxy --skip-auth-regex='.*'
oauth2-proxy --skip-auth-routes='GET=^.*$'
```

```toml
skip_auth_regex = [ "^/.*$" ]
```

…which fully bypasses the proxy. The upstream then receives
unauthenticated traffic from the public internet, defeating the
entire reason for deploying `oauth2-proxy`.

Upstream reference:

- <https://github.com/oauth2-proxy/oauth2-proxy>
- <https://oauth2-proxy.github.io/oauth2-proxy/configuration/overview>

## Heuristic

A file is "oauth2-proxy related" if it mentions one of:
- image `quay.io/oauth2-proxy/oauth2-proxy` or
  `bitnami/oauth2-proxy`
- the binary name `oauth2-proxy`
- any of the config keys: `skip_auth_regex`, `skip_auth_routes`,
  `skip-auth-regex`, `skip-auth-route`

Inside such a file, outside `#` / `//` comments, we flag any value
whose regex (after stripping a leading HTTP-method `=` prefix like
`GET=`) reduces to one of:

```
.*
^.*$  ^.*  .*$
^/.*$  ^/.*  /.*  /  ^/  ^
(?i).*
(.*)  ^(.*)$
```

Each occurrence emits one finding line.

## What we accept (no false positive)

- `--skip-auth-regex='^/healthz$'` — narrow.
- `skip_auth_regex = [ "^/api/public/v1/.*$" ]` — anchored to a
  specific public subtree.
- README / runbook that mentions the bad shape inside `#` / `//`
  comments only.

## What we flag

- `--skip-auth-regex='^.*$'` (Dockerfile CMD).
- `--skip-auth-regex=.*` (docker-compose command list).
- `skip_auth_regex = [ "^/healthz$", "^/.*$" ]` (cfg list).
- `--skip-auth-routes=GET=^.*$` (k8s args).

## Limits / known false negatives

- We do not reason about anchored alternations like
  `^/.*|/private` (which is also permissive). Add to
  `_PERMISSIVE` if you need it.
- We do not parse Helm values into a tree; we match scalar
  forms or simple yaml lists.
- We do not evaluate regex semantics; we only match a small
  curated list of obviously-permissive shapes.

## Usage

```bash
python3 detect.py path/to/repo/
python3 detect.py oauth2_proxy.cfg docker-compose.yaml
```

Exit codes: `0` = no findings, `1` = findings (printed to stdout),
`2` = usage error.

## Smoke test

```
$ bash smoke.sh
bad=4/4 good=0/3
PASS
```

Layout:

```
examples/bad/
  01_dockerfile_dotstar.Dockerfile         # --skip-auth-regex=^.*$
  02_compose_inline_dotstar.yaml           # --skip-auth-regex=.*
  03_oauth2_proxy.cfg                      # cfg list contains "^/.*$"
  04_k8s_skip_auth_routes_method.yaml      # --skip-auth-routes=GET=^.*$
examples/good/
  01_only_health_metrics.Dockerfile        # only ^/healthz$ + ^/metrics$
  02_scoped_paths.cfg                      # narrow public subtree only
  03_runbook_comment_only.conf             # bad form in comments only
```
