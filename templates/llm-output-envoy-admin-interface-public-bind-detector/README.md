# llm-output-envoy-admin-interface-public-bind-detector

Stdlib-only Python detector that flags **Envoy proxy** configurations
whose `admin` interface is bound to a publicly routable address
(`0.0.0.0`, `::`, an external IP, or a templated value we cannot
prove safe). Maps to **CWE-732: Incorrect Permission Assignment for
Critical Resource** and **CWE-668: Exposure of Resource to Wrong
Sphere**.

The Envoy admin endpoint exposes `/quitquitquit`, `/clusters`,
`/config_dump` (which can leak TLS material in some setups),
`/runtime`, and `/server_info`. Reachable from the network it is a
one-step path to draining traffic, dumping live cluster state, or
reading the running configuration.

LLMs reach for `0.0.0.0` because it "just works" inside containers
and because the difference between "loopback only" and "all
interfaces" is a single character.

## Heuristic

For each YAML / JSON file we walk:

1. Find an `admin:` block (YAML) or `"admin":` key (JSON).
2. Within the next ~30 non-blank lines, look for a `socket_address:`
   followed by `address: <value>`.
3. Loopback values are accepted silently: `127.0.0.0/8`, `::1`,
   `localhost`. Unix domain sockets (`pipe:` / `path:`) are also
   accepted.
4. Anything else -- `0.0.0.0`, `::`, `[::]`, an actual external IP,
   or `{{ .Values.host }}` / `${ENVOY_ADMIN_HOST}` -- is flagged.
   Templated values are flagged as **SENSITIVE** because we cannot
   prove what they will resolve to.

## CWE / standards

- **CWE-732**: Incorrect Permission Assignment for Critical Resource.
- **CWE-668**: Exposure of Resource to Wrong Sphere.
- Envoy upstream guidance: bind the admin interface to `127.0.0.1`
  or a Unix domain socket only.

## What we accept (no false positive)

- `address: 127.0.0.1`, `address: ::1`, `address: localhost`.
- `pipe:` / `path:` Unix socket addresses.
- `admin:` mentioned in a `#` comment.
- A non-admin listener bound to `0.0.0.0` (we only flag the `admin:`
  block).

## What we flag

- `address: 0.0.0.0` / `::` / `[::]` under `admin.address.socket_address`.
- Any non-loopback IPv4 / IPv6 literal.
- Templated bind value (`{{ .Values.x }}`, `${VAR}`) -- SENSITIVE.
- JSON form: `"admin": {"address": {"socket_address": {"address": "0.0.0.0"}}}`.
- An `admin:` block that declares no resolvable bind address (likely
  a truncated template) -- SENSITIVE.

## Limits / known false negatives

- We do not render Helm / Jinja templates first.
- We do not parse YAML; we line-window scan to tolerate templating.
- We do not flag insecure `runtime` paths, missing `--service-node`
  hardening, or a missing admin TLS context -- those are out of scope.

## Usage

```bash
python3 detect.py path/to/envoy.yaml
python3 detect.py path/to/configs/
```

Exit codes: `0` = no findings, `1` = findings (printed to stdout),
`2` = usage error.

## Smoke test

```
$ bash smoke.sh
bad=6/6 good=0/6
PASS
```

Layout:

```
examples/bad/
  01_wildcard_v4.yaml          # address: 0.0.0.0
  02_wildcard_v6.yaml          # address: "::"
  03_external_ip.yaml          # address: 10.0.5.42
  04_helm_templated.yaml       # address: {{ .Values.adminHost }}
  05_json_wildcard.json        # JSON form of 0.0.0.0
  06_envsubst_templated.yaml   # address: ${ENVOY_ADMIN_HOST}
examples/good/
  01_loopback_v4.yaml          # 127.0.0.1
  02_loopback_v6.yaml          # ::1
  03_unix_socket.yaml          # pipe: /var/run/envoy-admin.sock
  04_json_loopback.json        # JSON loopback
  05_listener_only_no_admin.yaml # public listener but NO admin block
  06_admin_in_comment.yaml     # admin: 0.0.0.0 only inside comments
```
