# llm-output-pulsar-authentication-disabled-detector

Stdlib-only Python detector that flags **Apache Pulsar** broker /
proxy / standalone configurations that disable authentication
(`authenticationEnabled=false`) or authorization
(`authorizationEnabled=false`).

Maps to **CWE-306** (Missing Authentication for Critical Function)
and **CWE-862** (Missing Authorization).

## Why this matters

Pulsar's broker (default port 6650 for the binary protocol, 8080
for the admin REST API) and proxy gate every produce, consume, and
admin call through `authenticationEnabled`. With that flag off,
anyone who can reach the broker port can:

- create / delete tenants, namespaces and topics,
- publish to and subscribe from any topic,
- read every retained message (Pulsar persists messages by default
  via BookKeeper, so historical data leaks too),
- reconfigure cluster-level policies and quotas through the admin
  REST API on port 8080 / 8443.

`authorizationEnabled=false` is functionally equivalent at the
edge: even with authentication on, the role attached to a JWT is
no longer consulted, so any authenticated client gets superuser
privileges on every namespace.

LLMs reach for these flags because every Pulsar quickstart guide
("get a broker running on your laptop in 60 seconds") ships with
auth off, and that quickstart config gets copy-pasted into Helm
values and Compose files unchanged.

## Heuristic

We flag, outside `#` / `//` comments:

1. `authenticationEnabled` set to a falsy value
   (`false`, `False`, `0`, `no`, `off`) in `broker.conf`,
   `proxy.conf`, `standalone.conf`, `*.properties`, `*.yaml`,
   or `*.yml`.
2. `authorizationEnabled` set to a falsy value in the same files.
3. Pulsar's standard env-var override prefix:
   `PULSAR_PREFIX_authenticationEnabled=false` (shell / Dockerfile)
   or `PULSAR_PREFIX_authenticationEnabled: "false"` (Compose /
   Helm YAML).
4. CLI flag form: `--authenticationEnabled=false` (commonly seen in
   Helm `extraArgs` lists).

Each occurrence emits one finding line.

## What we flag

- `authenticationEnabled=false` in `broker.conf` / `proxy.conf`.
- `PULSAR_PREFIX_authenticationEnabled: "false"` in
  `docker-compose.yml`.
- `--authenticationEnabled=false` in a Helm `extraArgs` list.
- `authorizationEnabled=false` in any Pulsar conf or YAML.

## What we accept

- `authenticationEnabled=true` with
  `authenticationProviders=...AuthenticationProviderToken`.
- Comment-only mentions:
  `# do NOT set authenticationEnabled=false in prod`.
- `auth.authentication.enabled: true` in Helm values.

## CWE / standards

- **CWE-306**: Missing Authentication for Critical Function.
- **CWE-862**: Missing Authorization.
- Apache Pulsar security docs:
  > Pulsar supports a pluggable authentication mechanism which
  > Pulsar clients can use to authenticate with brokers and proxies.

## Usage

```bash
python3 detect.py path/to/broker.conf
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
  01_broker_conf_auth_off.conf       # authenticationEnabled=false
  02_proxy_conf_auth_off.conf        # proxy.conf auth off
  03_docker_compose_env.yml          # PULSAR_PREFIX_... env override
  04_helm_values_args.yaml           # --authenticationEnabled=false
examples/good/
  01_broker_conf_auth_on.conf        # JWT auth + authz on
  02_docker_compose_auth_on.yml      # env override = "true"
  03_helm_values_auth_on.yaml        # auth.enabled: true
```

## Limits / known false negatives

- Programmatic configuration that builds the key from a runtime
  string (e.g. shell `echo "${KEY}=${VAL}" >> broker.conf`) is out
  of scope.
- We do not cross-check that the broker port is reachable on a
  routable interface; combined with `bindAddress=0.0.0.0` and no
  network policy, a finding here is critical.
- Sibling detectors in this series cover Pulsar TLS-disabled
  configs and broker JWT secret leakage.
