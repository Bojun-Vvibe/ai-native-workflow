# llm-output-kong-admin-api-public-bind-detector

Stdlib-only Python detector that flags **Kong Gateway** configurations
which bind the **Admin API** to a public interface — i.e.
`admin_listen` set to `0.0.0.0:8001` (or any non-loopback IP, or
the bare port form `8001`) in `kong.conf`, in a `KONG_ADMIN_LISTEN`
env override, in a `docker-compose` env list, or in a Helm values
override.

The Kong Admin API is an unauthenticated control plane: anyone who
can reach the listener can create / modify / delete services,
routes, plugins, consumers, and credentials, and can therefore
silently route traffic from production hostnames to attacker-
controlled upstreams. Kong's own deployment guide states that the
Admin API "must never be publicly exposed." Yet the most common
docker-compose snippets and Helm `extraEnv` blocks set
`KONG_ADMIN_LISTEN=0.0.0.0:8001` to make the API reachable from a
local browser, then ship that config straight to a public node.

Maps to:
- **CWE-306**: Missing Authentication for Critical Function.
- **CWE-668**: Exposure of Resource to Wrong Sphere.
- **CWE-1188**: Insecure Default Initialization of Resource.

## Heuristic

We flag any of the following, outside `#` comment lines:

1. `admin_listen = 0.0.0.0:NNNN` (or `[::]:NNNN`, or any IPv4
   that is not `127.0.0.1` / `::1` / `localhost`) in a `kong.conf`.
2. `KONG_ADMIN_LISTEN=0.0.0.0:NNNN` (or `[::]:NNNN`, or a non-
   loopback IP) as a shell env, Dockerfile `ENV`, docker-compose
   `environment` list, k8s container env, or `.env` file.
3. The bare-port form `admin_listen = 8001` / `KONG_ADMIN_LISTEN=
   8001` — Kong interprets a bare port as bind-on-all-interfaces.
4. The `off` / disabled form is the safe-by-default value and is
   NOT flagged. The loopback form `127.0.0.1:8001` is NOT flagged.

Each occurrence emits one finding line.

## CWE / standards

- **CWE-306**: Missing Authentication for Critical Function.
- **CWE-668**: Exposure of Resource to Wrong Sphere.
- **CWE-1188**: Insecure Default Initialization of Resource.
- Kong Gateway docs, "Securing the Admin API":
  "The Admin API provides full control of Kong, so it is important
  that this API is only available to those who require access and
  that it is appropriately secured. **Never expose the Admin API
  publicly.**"

## What we accept (no false positive)

- `admin_listen = 127.0.0.1:8001` (loopback only — the safe default).
- `admin_listen = off` (Admin API disabled entirely).
- `KONG_ADMIN_LISTEN=127.0.0.1:8001 ssl` and any other listen
  attributes appended after the address.
- Documentation / commented-out lines
  (`# admin_listen = 0.0.0.0:8001`).
- The `proxy_listen` directive — it MUST bind publicly; that's the
  data-plane port. We only flag `admin_listen` / `KONG_ADMIN_LISTEN`.
- `KONG_ADMIN_GUI_LISTEN` is the separate UI listener and is also
  flagged when it binds publicly without an auth plugin context;
  this detector treats it the same way.

## Layout

```
detect.py            stdlib-only scanner (regex over text)
smoke.sh             runs detect.py against examples/ and asserts
examples/bad/        4 fixtures that MUST be flagged
examples/good/       3 fixtures that MUST NOT be flagged
```

## Run

```
python3 detect.py path/to/kong.conf
python3 detect.py path/to/repo
bash smoke.sh
```

Exit codes: `0` = clean, `1` = findings, `2` = usage error.

## Why this is a real LLM failure mode

Every "I can't reach the Kong Admin API from my laptop" tutorial
solves the problem with `KONG_ADMIN_LISTEN=0.0.0.0:8001`. The
official quick-start container image ships with the safe loopback
binding, and the LLM-generated answer to "make the Admin API
reachable" is invariably to override it with the all-interfaces
bind. Once that env var is in a docker-compose file, a Helm chart,
or a Nomad job spec, it follows the deployment to a public VPC
where port 8001 is one security-group misconfiguration away from
full gateway takeover.
