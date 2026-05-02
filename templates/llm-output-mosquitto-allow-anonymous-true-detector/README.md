# llm-output-mosquitto-allow-anonymous-true-detector

Detects Mosquitto MQTT broker configuration files (`mosquitto.conf`) that
ship with anonymous clients allowed (`allow_anonymous true`) on a
listener that is reachable from a non-loopback interface and that has
no `password_file` / `psk_file` / `auth_plugin` configured.

## Why this matters

Mosquitto is the most widely deployed MQTT broker. With
`allow_anonymous true` on a public-facing listener, any client can
`SUBSCRIBE #` and read the entire bus, or `PUBLISH` arbitrary control
messages to topics owned by IoT devices, building automation, or
industrial PLCs. Shodan continually indexes thousands of such open
brokers.

LLM-generated tutorials and quickstart configs frequently include the
combination:

    listener 1883 0.0.0.0
    allow_anonymous true

because it is the path of least resistance to a working broker. The
detector flags that shape so the LLM caller can intercept it before
the config lands in a real deployment.

## What it detects

For each scanned file, the detector inspects the listener layout and
the auth directives and reports a finding when **all** of:

1. `allow_anonymous true` is present (this is the per-broker default
   when the directive is missing on Mosquitto < 2.0, but the detector
   only flags an explicit `true`).
2. At least one `listener` is bound to a non-loopback interface, OR
   the bare `port` directive is set with no `bind_address` of
   `127.0.0.1` / `::1`.
3. None of `password_file`, `psk_file`, or `auth_plugin` is configured
   on that listener (or globally).

Per-listener `allow_anonymous` overrides are honored: if a listener
block contains its own `allow_anonymous false`, that listener is
considered safe even if the global default is `true`.

## CWE references

- CWE-306: Missing Authentication for Critical Function
- CWE-284: Improper Access Control
- CWE-1188: Insecure Default Initialization of Resource

## False-positive surface

- Local development / docker-compose with broker on a private network.
  Suppress per file with a top comment `# mqtt-anonymous-allowed`.
- Brokers running TLS with client-certificate-only auth
  (`require_certificate true` + `use_identity_as_username true`) are
  treated as authenticated.

## Usage

    python3 detector.py path/to/mosquitto.conf

Exit code: number of files with at least one finding (capped at 255).
Stdout format: `<file>:<line>:<reason>`.

Run `bash verify.sh` to execute the bundled good/bad fixtures.
