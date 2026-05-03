# llm-output-flink-jobmanager-no-auth-detector

Defensive detector for LLM-generated Apache Flink configs that
expose the JobManager REST / Web UI on the network with **no
authentication**. Apache Flink ships **zero built-in authn** for
its REST endpoint -- if the port is reachable, anyone on the
network can submit / cancel jobs and upload JAR files (i.e. RCE).

## CWE / OWASP mapping

- **CWE-306**: Missing Authentication for Critical Function
- **CWE-749**: Exposed Dangerous Method or Function
- **CWE-1188**: Insecure Default Initialization of Resource
- **OWASP A05:2021**: Security Misconfiguration

Real CVEs that required this misconfig as a precondition:

- **CVE-2020-17518**: Flink REST file upload path traversal
- **CVE-2020-17519**: Flink REST unauthenticated arbitrary file read

## What it flags

A file is flagged when EITHER:

1. A Flink config sets a JobManager REST/UI bind to a non-loopback
   interface, e.g.

   ```yaml
   rest.bind-address: 0.0.0.0
   rest.address: 0.0.0.0
   jobmanager.bind-host: 0.0.0.0
   jobmanager.rpc.address: 0.0.0.0
   web.address: 0.0.0.0
   ```

   or the same key passed via CLI: `--rest.bind-address=0.0.0.0`,
   `-Drest.bind-address=0.0.0.0`.

2. A `docker-compose.*` or `Dockerfile*` publishes / `EXPOSE`s
   port `8081` from a Flink image with no auth proxy in the
   same file.

A finding is **suppressed** if the same file mentions an auth
proxy or mTLS:

- `oauth2-proxy`, `authelia`, `keycloak-gatekeeper`, `oidc-proxy`
- `basic_auth` / `htpasswd` / Traefik basicauth middleware
- `nginx.ingress.kubernetes.io/auth-*`
- `security.ssl.rest.enabled: true` (mTLS for REST)

Loopback binds (`127.0.0.1`, `localhost`, `::1`) are treated as
safe.

## Why LLMs ship this

Every Flink quickstart sets `rest.bind-address: 0.0.0.0` so the
dashboard "just works" from the host browser. Models replay the
quickstart wholesale into production manifests, helm values, and
compose stacks because Flink itself has no auth knob to flip.

## Usage

```bash
python3 detect.py path/to/flink-conf.yaml
python3 detect.py path/to/repo/  # walks the tree
```

Exit codes: `0` = clean, `1` = findings, `2` = usage error.

## Worked example

```bash
$ bash smoke.sh
bad=4/4 good=0/3
PASS
```

The four positive fixtures cover:

1. `flink-conf.yaml` with `rest.bind-address: 0.0.0.0`
2. `docker-compose.yml` publishing `8081:8081`
3. CLI `-Drest.bind-address=0.0.0.0` flag in a launch script
4. `Dockerfile` with `EXPOSE 8081` and `FLINK_PROPERTIES` set to
   bind everywhere

The three negative fixtures cover:

1. `flink-conf.yaml` bound to `127.0.0.1`
2. `docker-compose.yml` fronted by `oauth2-proxy`
3. A documentation file with the bad pattern only inside `#`
   comments

## Remediation

- Bind REST to loopback (`rest.bind-address: 127.0.0.1`) and
  tunnel via SSH / `kubectl port-forward`, OR
- Front the JobManager with an authenticating proxy
  (`oauth2-proxy`, `authelia`, Traefik basicauth middleware,
  nginx-ingress with `auth-url`), OR
- Enable mTLS for REST with
  `security.ssl.rest.enabled: true` plus a properly issued client
  certificate.

See:
<https://nightlies.apache.org/flink/flink-docs-stable/docs/deployment/security/security-rest/>
