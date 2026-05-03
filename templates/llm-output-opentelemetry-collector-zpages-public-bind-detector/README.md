# llm-output-opentelemetry-collector-zpages-public-bind-detector

Defensive detector for LLM-generated OpenTelemetry Collector
configs that enable the **`zpages`** extension and bind its HTTP
debug endpoint (default :55679) to a non-loopback interface.
zpages has **no authentication** and exposes:

- `/debug/tracez` — recent / sampled spans, including attribute
  values (request URLs, user IDs, internal hostnames, error
  stack traces, SQL fragments, payload data).
- `/debug/pipelinez` — receiver / processor / exporter topology.
- `/debug/extensionz` — enabled extensions and their config.

The contrib repo's own README warns: *"zpages should not be
exposed to the public internet as it can leak sensitive trace
data."*

## CWE / OWASP mapping

- **CWE-200**: Exposure of Sensitive Information to an
  Unauthorized Actor
- **CWE-306**: Missing Authentication for Critical Function
- **CWE-668**: Exposure of Resource to Wrong Sphere
- **CWE-1188**: Insecure Default Initialization of Resource
- **OWASP A05:2021**: Security Misconfiguration

## What it flags

A YAML file is flagged when ALL of:

1. The file looks like an OpenTelemetry Collector config
   (has at least two of `receivers:` / `exporters:` /
   `processors:` / `extensions:` / `service:` / `pipelines:` /
   `otlp:` / `otlphttp:`).
2. An `extensions:` block defines `zpages:` (or a named
   instance like `zpages/primary:`) with an `endpoint:` whose
   host is `0.0.0.0`, `::`, `[::]`, `*`, or empty (e.g.
   `":55679"`).
3. The extension is referenced from `service.extensions:`
   (either the list-of-strings form or the inline `[zpages]`
   form), OR there is no `service:` block at all in the file
   (snippet form — flag conservatively).

We also independently flag `docker-compose.*` /
`Dockerfile*` files that publish / `EXPOSE` port `55679` from
an `otel/opentelemetry-collector` (or `-contrib`) image.

A finding is **suppressed** if the same file mentions a
fronting auth proxy (`oauth2-proxy`, `authelia`,
`keycloak-gatekeeper`, `oidc-proxy`, basic auth, htpasswd,
Traefik basicauth middleware, or
`nginx.ingress.kubernetes.io/auth-*`).

Loopback binds (`127.0.0.1`, `localhost`, `::1`) are treated
as safe.

## Why LLMs ship this

The collector's quickstart YAML wires `zpages` for "easy
debugging from the host browser". Models replay that
wholesale into production manifests and Helm charts, often
also rewriting `localhost:55679` to `0.0.0.0:55679` so the
page is reachable from outside the container. zpages itself
has no auth knob.

## Usage

```bash
python3 detect.py path/to/otel-config.yaml
python3 detect.py path/to/repo/   # walks the tree
```

Exit codes: `0` = clean, `1` = findings, `2` = usage error.

## Worked example

```bash
$ bash smoke.sh
bad=4/4 good=0/3
PASS
```

The four positive fixtures cover:

1. `zpages: endpoint: 0.0.0.0:55679` and enabled in
   `service.extensions`.
2. `zpages: endpoint: ":55679"` (empty host == all interfaces).
3. Named instance `zpages/primary:` bound to `[::]:55679`.
4. `docker-compose.yml` publishing `55679:55679` from the
   `otel/opentelemetry-collector-contrib` image.

The three negative fixtures cover:

1. `zpages: endpoint: 127.0.0.1:55679` (loopback-only).
2. `zpages` defined but **not** listed under
   `service.extensions:` (collector won't start it).
3. A documentation file with the bad pattern only inside `#`
   comments.

## Remediation

- Bind to loopback (`endpoint: 127.0.0.1:55679`) and reach via
  SSH tunnel or `kubectl port-forward`, OR
- Remove `zpages` from the `service.extensions:` list in
  production deployments, OR
- Front the collector with an authenticating proxy
  (`oauth2-proxy`, `authelia`, Traefik basicauth, nginx-ingress
  with `auth-url`) and restrict the path `/debug/*` to
  authenticated operators.

See:
<https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/extension/zpagesextension>
