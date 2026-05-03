# llm-output-emqx-allow-anonymous-true-detector

Stdlib-only Python detector that flags **EMQX** MQTT broker configs
that allow anonymous client connections. Maps to **CWE-306** (missing
authentication for critical function), **CWE-1188** (insecure default
initialization), and **CWE-285** (improper authorization, when paired
with EMQX's default `allow all` ACL).

When `allow_anonymous = true` (or any of the equivalent surfaces
below) is shipped, any TCP client that can reach the broker can
publish and subscribe to every topic without presenting credentials.
For an MQTT broker that typically carries IoT telemetry, control
commands, and bridge traffic, this is a full data-plane bypass.

## Heuristic

Outside `#` / `//` comments, we flag:

1. `allow_anonymous = true` / `allow_anonymous: true` (classic
   `emqx.conf` / HOCON)
2. `mqtt.allow_anonymous = true` (dotted HOCON key)
3. `EMQX_ALLOW_ANONYMOUS=true` and `EMQX_MQTT__ALLOW_ANONYMOUS=true`
   (env / compose / helm values)
4. `authentication = []` / `authentication: []` (empty list disables
   the EMQX 5.x authenticator chain entirely)

Boolean parsing accepts `true`, `True`, `TRUE`, and quoted forms.

## Files scanned

- `emqx.conf`, `*.conf`, `*.hocon`
- `*.yaml`, `*.yml`, `*.toml`
- `Dockerfile`, `docker-compose.*`
- `*.sh`, `*.bash`, `*.service`, `*.envconf`

We deliberately do **not** scan `*.env` files (the repo guardrail
blocks paths matching `*.env`); name env-style fixtures `*.envconf`.

## Usage

```sh
python3 detect.py path/to/emqx.conf
python3 detect.py path/to/dir/
```

Exit codes: `0` = no findings, `1` = findings, `2` = usage error.

## Smoke

```sh
./smoke.sh
```

Expects `bad=6/6 good=6/6` (all bad fixtures flagged, no false
positives on good fixtures).
