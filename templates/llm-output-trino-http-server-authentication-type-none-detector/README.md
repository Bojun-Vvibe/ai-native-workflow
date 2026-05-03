# llm-output-trino-http-server-authentication-type-none-detector

Stdlib-only Python detector that flags **Trino** (and the legacy
PrestoSQL fork) coordinator configurations that disable HTTP
authentication on the coordinator -- either by setting
`http-server.authentication.type=NONE`, by listing `NONE` in a
multi-authenticator list, or by enabling
`http-server.authentication.allow-insecure-over-http=true`.

Maps to **CWE-306** (Missing Authentication for Critical Function),
**CWE-287** (Improper Authentication), and **CWE-319** (Cleartext
Transmission of Sensitive Information).

## Why this matters

Trino's coordinator (default port 8080 for HTTP, 8443 for HTTPS)
exposes:

- the `/v1/statement` endpoint that runs SQL as whichever user the
  client claims to be -- the `X-Trino-User` HTTP header is trusted
  verbatim when no authenticator is wired in;
- `/v1/jmx`, `/v1/node`, `/v1/thread`, and `/v1/info`, which leak
  cluster topology, JVM internals and version info;
- `/v1/cluster` and the `/ui/` web console, which can kill running
  queries.

When `http-server.authentication.type` is set to `NONE` (or omits
authentication entirely) and the coordinator listens on a routable
interface, anyone who can reach port 8080 can run SQL as
`root` / `admin` / any chosen user against every catalog the
coordinator can see (Hive, Iceberg, MySQL, Postgres, S3, etc.).

LLMs reach for `http-server.authentication.type=NONE` because
every Trino quickstart ships that way ("get queries running, then
add auth later"), and that quickstart config gets copy-pasted into
production Helm values unchanged.

## Heuristic

We flag, outside `#` / `//` comments:

1. `http-server.authentication.type` whose value contains `NONE`
   (case-insensitive). Trino accepts a comma-separated list like
   `PASSWORD,JWT`; we flag when `NONE` appears in the list -- the
   coordinator will accept any of the listed mechanisms, so any
   request can choose `NONE`.
2. `http-server.authentication.allow-insecure-over-http=true` (any
   truthy value: `true`, `1`, `yes`, `on`).
3. CLI / env override form via the launcher:
   `TRINO_HTTP_SERVER_AUTHENTICATION_TYPE=NONE` or
   `PRESTO_HTTP_SERVER_AUTHENTICATION_TYPE=NONE`.

Each occurrence emits one finding line.

## What we flag

- `http-server.authentication.type=NONE` in `config.properties`.
- `http-server.authentication.type=PASSWORD,JWT,NONE`.
- `http-server.authentication.allow-insecure-over-http=true`.
- `TRINO_HTTP_SERVER_AUTHENTICATION_TYPE: "NONE"` in
  `docker-compose.yml`.

## What we accept

- `http-server.authentication.type=PASSWORD` with a password
  authenticator config file pinned.
- `http-server.authentication.type=OAUTH2` against a real IdP.
- `http-server.authentication.type=JWT` with a JWKS URL configured.
- Comment-only mentions: `# do NOT set ...=NONE in prod`.

## CWE / standards

- **CWE-306**: Missing Authentication for Critical Function.
- **CWE-287**: Improper Authentication.
- **CWE-319**: Cleartext Transmission of Sensitive Information
  (the `allow-insecure-over-http` case).
- Trino security docs:
  > By default, the Trino coordinator does not require any
  > authentication... configure an authentication mechanism before
  > exposing the coordinator to untrusted networks.

## Usage

```bash
python3 detect.py path/to/config.properties
python3 detect.py path/to/repo/
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
  01_config_properties_type_none.properties             # type=NONE
  02_config_properties_type_list_with_none.properties   # PASSWORD,JWT,NONE
  03_allow_insecure_over_http.properties                # insecure-over-http=true
  04_docker_compose_env_none.yml                        # TRINO_*=NONE env
examples/good/
  01_config_properties_password_auth.properties         # PASSWORD on HTTPS
  02_config_properties_oauth2.properties                # OAUTH2 with IdP
  03_docker_compose_jwt.yml                             # JWT env
```

## Limits / known false negatives

- Configurations that build the property name from a runtime
  template (Jinja / envsubst) are out of scope.
- We do not cross-check that the coordinator is bound to a routable
  interface; combined with `http-server.http.port=8080` on `0.0.0.0`
  and no network policy, a finding here is critical.
- Sibling detectors in this series cover Trino TLS-disabled
  coordinators and shared-secret leakage in `internal-shared-secret`.
