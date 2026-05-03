# llm-output-kafka-connect-rest-no-auth-detector

Defensive detector for LLM-generated Apache Kafka Connect worker
configurations that expose the REST API (default :8083) on the
network with **no authentication**. Kafka Connect ships **zero
built-in REST authn** -- if the port is reachable, anyone on the
network can create / pause / delete connectors and load plugin
classes from the worker's classpath (i.e. RCE pivot).

## CWE / OWASP mapping

- **CWE-306**: Missing Authentication for Critical Function
- **CWE-749**: Exposed Dangerous Method or Function
- **CWE-1188**: Insecure Default Initialization of Resource
- **OWASP A05:2021**: Security Misconfiguration

Real CVEs / incidents that required this misconfig as a
precondition:

- **CVE-2023-25194**: Kafka Connect JNDI deserialization via
  attacker-controlled connector config submitted to the REST API.

## What it flags

A file is flagged when EITHER:

1. A Kafka Connect worker config sets a REST listener bind to a
   non-loopback interface, e.g.

   ```properties
   rest.host.name=0.0.0.0
   rest.advertised.host.name=0.0.0.0
   listeners=http://0.0.0.0:8083
   listeners=http://:8083              # empty host == all-ifaces
   ```

   or the same key passed via CLI:
   `--override rest.host.name=0.0.0.0`.

2. A `docker-compose.*` (or any compose file referencing a
   `cp-kafka-connect` / `debezium/connect` / `kafka-connect`
   image) or `Dockerfile*` publishes / `EXPOSE`s port `8083`
   from a Kafka Connect image with no auth proxy in the same
   file.

A finding is **suppressed** if the same file mentions a REST
auth extension or an auth proxy:

- `rest.extension.classes=...BasicAuthSecurityRestExtension`
- `rest.extension.classes=<any non-empty value>` (custom extension)
- `oauth2-proxy`, `authelia`, `keycloak-gatekeeper`, `oidc-proxy`
- `htpasswd`, Traefik basicauth middleware
- `nginx.ingress.kubernetes.io/auth-*`
- `listeners.https.ssl.client.auth=required|requested` (mTLS)

Loopback binds (`127.0.0.1`, `localhost`, `::1`) are treated as
safe.

## Why LLMs ship this

Every Kafka Connect quickstart sets `rest.host.name=0.0.0.0` so
the REST API is reachable from the host browser. Because Connect
itself has no auth knob to flip out of the box, models replay the
quickstart wholesale into production manifests and helm charts
without adding `rest.extension.classes` or a fronting proxy.

## Usage

```bash
python3 detect.py path/to/connect-distributed.properties
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

1. `connect-distributed.properties` with `rest.host.name=0.0.0.0`
2. `connect-distributed.properties` using
   `listeners=http://0.0.0.0:8083`
3. `docker-compose.yml` publishing `8083:8083` from a
   `cp-kafka-connect` image
4. A launch script using
   `--override rest.host.name=0.0.0.0`

The three negative fixtures cover:

1. `connect-distributed.properties` bound to `127.0.0.1`
2. `connect-distributed.properties` with
   `BasicAuthSecurityRestExtension` configured
3. A documentation file with the bad pattern only inside `#`
   comments

## Remediation

- Bind REST to loopback (`rest.host.name=127.0.0.1`) and tunnel
  via SSH or `kubectl port-forward`, OR
- Configure the bundled basic-auth REST extension:

  ```properties
  rest.extension.classes=org.apache.kafka.connect.rest.basic.auth.extension.BasicAuthSecurityRestExtension
  ```

  plus a JAAS file pointed at a credentials properties file, OR
- Front the worker with an authenticating proxy (`oauth2-proxy`,
  `authelia`, Traefik basicauth middleware, nginx-ingress with
  `auth-url`), OR
- Switch to `listeners=https://...:8083` and require client certs
  with `listeners.https.ssl.client.auth=required`.

See: <https://kafka.apache.org/documentation/#connect_rest>
