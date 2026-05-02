# llm-output-kafka-plaintext-listener-detector

Static lint that flags Kafka broker configurations
(`server.properties`) which expose a `PLAINTEXT://` listener on a
non-loopback interface — i.e. accept producer/consumer/admin traffic
without TLS or SASL.

The default listener name `PLAINTEXT` maps, by default, to the
`PLAINTEXT` security protocol — *no TLS, no SASL, no auth, no
encryption*. Anyone who can route packets to the port can produce,
consume, list topics, and (with the still-common default-allow ACLs)
issue admin RPCs.

LLMs asked to "give me a quick Kafka config" routinely paste:

```properties
listeners=PLAINTEXT://0.0.0.0:9092
advertised.listeners=PLAINTEXT://kafka.internal:9092
```

…which is fine for a single-host docker-compose dev box but
catastrophic on any shared network.

## What it catches

A line in a Kafka properties file where, after stripping comments:

- The key is `listeners` or `advertised.listeners`; AND
- At least one comma-separated entry has scheme `PLAINTEXT://` (or a
  custom listener name remapped to `PLAINTEXT` via
  `listener.security.protocol.map` in the same file); AND
- The host portion is not loopback (`127.0.0.1`, `::1`, `localhost`).

Hosts flagged:

- `0.0.0.0`, `[::]` (all interfaces) — loudest finding.
- Any concrete non-loopback IPv4/IPv6 or hostname.
- Empty host (`PLAINTEXT://:9092`) — Kafka binds all interfaces.

## What it does NOT flag

- `PLAINTEXT://127.0.0.1:9092` and `PLAINTEXT://localhost:9092`.
- Listeners with scheme `SSL://`, `SASL_SSL://`, or `SASL_PLAINTEXT://`
  on any host.
- Lines suppressed with a trailing `# kafka-plaintext-ok` comment.
- Files containing `# kafka-plaintext-ok-file` anywhere.
- Custom listener names explicitly remapped to `SSL` / `SASL_SSL` in
  `listener.security.protocol.map`.

## CWE references

- [CWE-319](https://cwe.mitre.org/data/definitions/319.html):
  Cleartext Transmission of Sensitive Information
- [CWE-306](https://cwe.mitre.org/data/definitions/306.html):
  Missing Authentication for Critical Function
- [CWE-200](https://cwe.mitre.org/data/definitions/200.html):
  Exposure of Sensitive Information

## False-positive surface

- Loopback-only PLAINTEXT for a developer laptop: not flagged.
- Embedded test brokers in CI fixtures: suppress with
  `# kafka-plaintext-ok-file` at the top of the file.
- Mesh-network scenarios where a sidecar terminates TLS: suppress on
  the specific listener line with `# kafka-plaintext-ok`.

## Verification

```text
$ ./verify.sh
bad=5/5 good=0/4
PASS
```

Per-file output:

```text
$ python3 detector.py examples/bad/01-all-interfaces/server.properties
examples/bad/01-all-interfaces/server.properties:2:listeners=PLAINTEXT://0.0.0.0:9092: PLAINTEXT listener bound to all interfaces (0.0.0.0)
examples/bad/01-all-interfaces/server.properties:3:advertised.listeners=PLAINTEXT://kafka.internal:9092: PLAINTEXT listener bound to non-loopback host kafka.internal

$ python3 detector.py examples/bad/05-custom-name-mapped-plain/server.properties
examples/bad/05-custom-name-mapped-plain/server.properties:3:listeners=INTERNAL://0.0.0.0:9092: PLAINTEXT listener bound to all interfaces (0.0.0.0)

$ python3 detector.py examples/good/04-custom-remapped-to-ssl/server.properties ; echo rc=$?
rc=0
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=Y_clean/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — 5 configs that MUST flag (all-interfaces, public
  IP, empty host, IPv6 any, custom-name-remapped-to-PLAINTEXT).
- `examples/good/` — 4 configs that MUST stay clean (loopback only,
  SSL only, SASL_SSL only, custom names remapped to SSL/SASL_SSL).
