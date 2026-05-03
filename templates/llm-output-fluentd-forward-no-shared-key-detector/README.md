# llm-output-fluentd-forward-no-shared-key-detector

Stdlib-only Python detector that flags **Fluentd** / **Fluent Bit**
`forward` input listeners configured WITHOUT a `shared_key`. Maps to
**CWE-306** (missing authentication for critical function),
**CWE-287** (improper authentication), and **CWE-1188** (insecure
default initialization).

The Fluentd `forward` input speaks the binary forward protocol,
typically on TCP/24224. Without `<security> shared_key </security>`
(and ideally `self_hostname` + per-client `<client>` blocks), ANY
process able to reach the port can:

- inject arbitrary log events into downstream sinks (S3, Elasticsearch,
  Kafka, Loki) under any `tag` it chooses;
- forge log records that look like they came from production hosts;
- trigger `@type exec` / `@type http` output plugins that downstream
  operators trust because "logs only come from our own agents".

This is the Fluentd equivalent of running an open SMTP relay, but
for logs. The Fluentd security guide explicitly requires `shared_key`
for any forward listener exposed beyond loopback.

LLMs ship this misconfig because the in_forward "hello world" snippet
in every blog post is a 3-line `<source> @type forward </source>`
with no security block, and because Fluent Bit's `[INPUT] Name forward`
appears with no shared-key hint in its quickstart docs.

## Heuristic

We parse Fluentd-style `<source>...</source>` blocks and Fluent Bit
`[INPUT] ... Name forward` stanzas:

**Fluentd source block** is flagged when:

- it contains `@type forward` (or legacy `type forward`), AND
- it does NOT contain a nested `<security>` block with a
  `shared_key` directive, AND
- it is not bound to `127.0.0.1` / `::1` / `localhost`.

**Fluent Bit `[INPUT]` section** is flagged when:

- it has `Name forward`, AND
- it does NOT contain a `Shared_Key` line, AND
- it is not `Listen 127.0.0.1` / `::1` / `localhost`.

Each occurrence emits one finding line.

## CWE / standards

- **CWE-306**: Missing Authentication for Critical Function.
- **CWE-287**: Improper Authentication.
- **CWE-1188**: Insecure Default Initialization of Resource.
- Fluentd security guide: forward listeners MUST set `shared_key`
  unless bound to loopback.

## What we accept (no false positive)

- `<source> @type forward </source>` with `<security> shared_key X </security>`.
- Loopback-only listener (`bind 127.0.0.1` or `Listen 127.0.0.1`).
- Forward OUTPUT plugins (`<match> @type forward </match>`) -- those
  are clients, not servers.
- Other input types (`@type tail`, `@type http`, `@type syslog`).

## What we flag

- Open `<source> @type forward </source>` with no `<security>` block.
- `<source>` blocks where `<security>` exists but only sets
  `self_hostname` / `user_auth false` -- still no `shared_key`.
- Fluent Bit `[INPUT] Name forward` exposed on `0.0.0.0` with no
  `Shared_Key`.
- Legacy `type forward` (pre-Fluentd 1.x) syntax.

## Limits / known false negatives

- We don't validate the *strength* of `shared_key` (a literal
  `shared_key changeme` will pass). A separate detector covers
  weak/default credentials.
- We don't cross-check `<client>` / `users` blocks for per-client
  auth.
- TLS settings (`<transport tls>`) are not inspected here.

## Usage

```bash
python3 detect.py path/to/fluent.conf
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
  01_open_forward.conf          # @type forward, bind 0.0.0.0, no security
  02_legacy_type.conf           # legacy `type forward`, no security
  03_security_no_key.conf       # <security> exists but no shared_key
  04_fluentbit_no_key.conf      # [INPUT] Name forward, Listen 0.0.0.0
examples/good/
  01_shared_key.conf            # <security> shared_key ${ENV}
  02_loopback_only.conf         # bind 127.0.0.1
  03_fluentbit_with_key.conf    # Fluent Bit with Shared_Key
```
