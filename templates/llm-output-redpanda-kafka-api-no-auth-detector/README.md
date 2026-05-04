# llm-output-redpanda-kafka-api-no-auth-detector

Detect Redpanda configuration snippets emitted by LLMs that expose the
Kafka API on a non-loopback bind without enabling SASL or mutual TLS.

## Why it matters

Redpanda is a Kafka-API-compatible streaming broker. Out of the box,
the Kafka API listens on `0.0.0.0:9092` with **no authentication and
no TLS** - any client that can route to port 9092 can produce, consume,
and run admin RPCs. The supported way to gate it is to:

- declare `kafka_api_tls:` with `enabled: true` **and**
  `require_client_auth: true`, **and/or**
- set `enable_sasl: true` (or `authentication_method: sasl` on the
  matching listener).

LLMs frequently produce a `redpanda.yaml` that binds Kafka API to
`0.0.0.0`, sometimes adds a `superusers:` list to look like it's
locked down, but never enables SASL.

## Rules

| # | Pattern | Why it matters |
|---|---------|----------------|
| 1 | `kafka_api:` listener bound to non-loopback (`0.0.0.0`, public IP) with no `enable_sasl: true` and no `kafka_api_tls.require_client_auth: true` | Anyone routable to the broker can produce / consume |
| 2 | CLI / helm `redpanda.kafka_api[N].address=0.0.0.0` (or any non-loopback) with no `redpanda.enable_sasl=true` and no mTLS requirement | Same exposure via rpk / helm overrides |
| 3 | `kafka_api_tls.enabled: true` but `require_client_auth: false` and `enable_sasl` not true | TLS is on, but anyone with the server cert connects anonymously |
| 4 | `superusers:` declared but `enable_sasl` is not true | Superuser list is a no-op without SASL turned on (LLMs include this as cosmetic security) |

`#`-comments are stripped before matching, so a doc that *warns*
against the insecure default does not trigger.

## Suppression

Add `# redpanda-public-readonly-ok` anywhere in the file to disable
all rules (intentional public broker, e.g. a benchmark cluster).

## Usage

```bash
python3 detector.py path/to/redpanda.yaml
python3 detector.py manifests/*.yaml          # exit code = #files with findings
helm template redpanda/redpanda | python3 detector.py
```

Output format:

```
manifests/redpanda.yaml:21: kafka_api bound to '0.0.0.0' without enable_sasl/authentication_method=sasl and without kafka_api_tls require_client_auth
manifests/redpanda.yaml:8:  superusers declared but enable_sasl is not true - superuser list is a no-op without SASL
```

## Tests

```bash
bash test.sh
# or
python3 test.py
```

Both run the detector against `examples/bad/*` (must all flag) and
`examples/good/*` (must all pass clean), printing
`PASS bad=4/4 good=0/3` on success.
