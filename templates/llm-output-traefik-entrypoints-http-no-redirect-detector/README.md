# llm-output-traefik-entrypoints-http-no-redirect-detector

Detect Traefik static configurations (YAML, TOML, or CLI flags) that
define a cleartext HTTP entrypoint (`:80` or `:8080`) **without** an
HTTP→HTTPS redirection on that entrypoint.

## What this catches

Traefik's recommended pattern when terminating TLS is:

```yaml
entryPoints:
  web:
    address: ":80"
    http:
      redirections:
        entryPoint:
          to: websecure
          scheme: https
          permanent: true
  websecure:
    address: ":443"
```

LLMs frequently emit a config that defines both `web` and `websecure`
but forgets the `redirections` block. Operators see ":80 is open and
:443 works" and ship it -- leaving every browser that types the
hostname without `https://` to talk plain HTTP forever, leaking
session cookies, bearer tokens, and auth headers.

This detector flags any cleartext entrypoint whose block does **not**
contain a `redirections.entryPoint.to` pointing at another
entrypoint.

## Detector logic

`detector.py` is stdlib-only Python 3.

1. Parse the input as YAML / TOML / CLI-flag soup using indent-aware
   text scans (no third-party YAML / TOML library).
2. Build the set of entrypoints whose `address` is `:80` or `:8080`.
3. Build the set of entrypoints with a `redirections.entryPoint.to`
   directive (matched in YAML blocks, TOML headers
   `[entryPoints.<name>.http.redirections.entryPoint]`, or CLI flags
   `--entrypoints.<name>.http.redirections.entrypoint.to=...`).
4. If any cleartext entrypoint is not in the redirected set, print
   `BAD` and exit 1. Otherwise print `GOOD` and exit 0.

Comments (`#`-prefixed lines) are stripped before matching.

## How to run

```bash
python3 detector.py bad/case-1.yaml    # -> BAD  (exit 1)
python3 detector.py good/case-1.yaml   # -> GOOD (exit 0)

bash worked-example.sh                 # all 7 fixtures + asserts
```

## Layout

```
detector.py
worked-example.sh
bad/
  case-1.yaml   # YAML web/websecure pair, no redirect
  case-2.toml   # TOML [entryPoints.web] address=":80", no redirect
  case-3.yaml   # docker-compose CLI args, no redirect flag
  case-4.yaml   # Helm additionalArguments, no redirect flag
good/
  case-1.yaml   # web + redirections.entryPoint.to: websecure
  case-2.toml   # [entryPoints.web.http.redirections.entryPoint]
  case-3.yaml   # CLI flags including redirections.entrypoint.to
```

## Limitations

- Only ports 80 and 8080 are treated as cleartext. A custom HTTP
  entrypoint on, e.g., `:8088` would slip past. Extend
  `CLEARTEXT_PORTS` if your environment uses other ports.
- The detector does not validate that the redirect target itself is
  actually a TLS-terminating entrypoint. A redirect from `web` to
  another cleartext entrypoint would still pass.
- Dynamic / file-provider middlewares that perform redirection at the
  router level (rather than the entrypoint level) are out of scope --
  they are far less common and handled by a separate detector family.
