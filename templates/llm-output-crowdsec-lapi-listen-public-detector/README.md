# llm-output-crowdsec-lapi-listen-public-detector

Static detector for CrowdSec configurations whose **Local API (LAPI)**
is bound to a public / wildcard interface without TLS or
agent-level mutual auth.

## Why

The CrowdSec installer ships LAPI bound to `127.0.0.1:8080`
intentionally — bouncers and the agent talk to it over loopback.
Operators distributing bouncers across hosts frequently change
`api.server.listen_uri` to `0.0.0.0:8080` or `[::]:8080` (or set the
`LAPI_LISTEN_URI` env var to the same) without enabling
`tls:` underneath. The result: the bouncer enrollment HTTP API,
which mints long-lived API keys and accepts decision pushes, is
reachable from any network the host can see — typically the public
internet.

This detector flags four shapes:

1. `config.yaml` (`/etc/crowdsec/config.yaml`) where
   `api.server.listen_uri` resolves to `0.0.0.0:<port>`,
   `[::]:<port>`, `*:<port>`, or a missing-host form like `:8080`
   **without** an adjacent `api.server.tls:` block.
2. Same file with `listen_uri` set to a public-looking literal
   (any non-loopback / non-link-local IPv4 host).
3. `docker-compose.yml` env block exporting
   `LAPI_LISTEN_URI=0.0.0.0:8080` (or the same wildcard variants).
4. `Dockerfile` / shell `crowdsec` invocations passing
   `--listen-uri 0.0.0.0:8080` (or with the wildcard variants).

## When to use

- Reviewing LLM-emitted CrowdSec install snippets before applying.
- Pre-merge gate on `infra/security/crowdsec/**` config repos.
- Spot check on container image build scripts.

## Suppression

Same line or the line directly above:

```
# crowdsec-lapi-listen-public-allowed
```

Use sparingly — typically only for in-cluster LAPI fronted by a
mesh/mTLS layer or a private overlay that is itself enforcing auth.

## How to run

```sh
./verify.sh
```

This runs `detector.py` against every fixture under `examples/bad`
and `examples/good` and prints a `bad=N/N good=0/N PASS` summary.

## Direct invocation

```sh
python3 detector.py path/to/config.yaml
```

Exit code is the number of files with at least one finding (capped
at 255). Stdout lines are formatted `<file>:<line>:<reason>`.

## Limitations

- TLS detection is structural: the detector looks for a `tls:` key
  inside the same `api.server:` block. If TLS is configured via a
  separate include file, point the detector at every include in the
  same invocation.
- The detector flags wildcard binds; it does not inspect host
  firewall rules. A wildcard bind behind a strict host firewall is
  still flagged — suppress per the section above if intentional.
