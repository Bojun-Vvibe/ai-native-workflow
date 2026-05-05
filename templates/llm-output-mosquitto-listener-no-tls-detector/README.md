# llm-output-mosquitto-listener-no-tls-detector

Detect Mosquitto MQTT broker configurations that LLMs commonly emit with a
non-loopback `listener` and **no TLS material**. The MQTT spec defines port
`1883` as cleartext and `8883` as the TLS port; the spec itself states that
authentication credentials sent over a cleartext listener "may be visible
to any party with access to the network". When asked "set up an MQTT
broker for my IoT fleet", LLMs routinely answer with `listener 1883
0.0.0.0`, `allow_anonymous false`, and a `password_file` — but no
`cafile` / `certfile` / `keyfile`. The username and password (and every
payload) then crosses the public internet in cleartext.

This detector is orthogonal to `llm-output-mosquitto-allow-anonymous-true-detector`,
which targets the unauthenticated-access failure mode. This one fires even
when authentication is configured, because cleartext authentication on a
public listener is itself the bug.

Related weaknesses: CWE-319 (Cleartext Transmission of Sensitive
Information), CWE-523 (Unprotected Transport of Credentials).

## What bad LLM output looks like

A listener bound to every interface with no TLS keys:

```
listener 1883 0.0.0.0
allow_anonymous false
password_file /etc/mosquitto/passwd
```

A listener with no address (Mosquitto binds to all interfaces by default):

```
listener 1883
allow_anonymous false
password_file /etc/mosquitto/passwd
```

Legacy single-listener form with no `bind_address` and no TLS:

```
port 1883
allow_anonymous false
password_file /etc/mosquitto/passwd
```

A Dockerfile baking the cleartext invocation into `CMD` with no `-c`
config pointer:

```dockerfile
CMD ["mosquitto", "-p", "1883"]
```

## What good LLM output looks like

- A loopback-only cleartext listener for in-host bridges, paired with a
  TLS listener on `8883` for remote clients.
- A TLS-only listener that declares `cafile`, `certfile`, `keyfile`, and
  ideally `require_certificate true` for mTLS.
- Legacy `port 1883` form pinned with `bind_address 127.0.0.1`.
- A Dockerfile `CMD` that passes `-c /path/to/mosquitto.conf` so the
  declared TLS listener is the one that runs.

## Run the smoke test

```sh
bash detect.sh samples/bad/* samples/good/*
```

Expected output:

```
BAD  samples/bad/dockerfile_mosquitto_cleartext.Dockerfile
BAD  samples/bad/legacy_port_1883_no_bind_no_tls.conf
BAD  samples/bad/listener_bind_all_no_tls.conf
BAD  samples/bad/listener_no_addr_no_tls.conf
GOOD samples/good/dockerfile_mosquitto_with_conf.Dockerfile
GOOD samples/good/legacy_port_1883_loopback.conf
GOOD samples/good/loopback_plus_tls_listener.conf
GOOD samples/good/tls_only_listener.conf
bad=4/4 good=0/4 PASS
```

Exit status is `0` only when every bad sample is flagged and zero good
samples are flagged.

## Detector rules

A file is in scope only if it contains one of `listener <port>`,
`mosquitto`, `allow_anonymous`, `bind_address`, or `persistence_location`.

A `listener` block runs from one `listener` line to the next; rules are
evaluated per block.

1. `listener <port> <addr>` where `<addr>` is not `127.0.0.1` / `::1` /
   `localhost` AND the block has no `cafile` / `certfile` / `keyfile` /
   `capath`.
2. `listener <port>` with no address (Mosquitto binds to every interface
   by default) AND the block has no TLS material.
3. Legacy top-level `port 1883` with no `bind_address` (or a non-loopback
   `bind_address`) AND no top-level TLS keys, AND no other `listener`
   directive in the file.
4. Invocation-style `mosquitto` with `-p 1883` and no `--cafile` /
   `--cert` / `--key` / `--capath` / `--tls-version` AND no `-c <conf>`
   (so we cannot claim a referenced config makes it safe). JSON-array
   `CMD ["...","..."]` form is normalized so flags split across array
   elements still match.

Shell `#` comments are stripped before matching.

## Known false-positive notes

- If the broker sits behind a TLS-terminating reverse proxy (e.g.,
  HAProxy doing SNI passthrough that decrypts before forwarding to a
  loopback `listener 1883 127.0.0.1`), the loopback rule already keeps
  the detector quiet.
- A `listener 1883` block paired with `proxy_protocol_v2_required true`
  and a TLS-only frontend may legitimately omit TLS material; this
  detector cannot see the upstream and will still flag it. Suppress per-
  file via your repo's existing detector-suppression mechanism.
- `tls_version` alone (no key/cert/cafile) does not satisfy the
  detector: the listener is still effectively cleartext.
