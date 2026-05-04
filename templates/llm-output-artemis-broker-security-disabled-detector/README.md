# llm-output-artemis-broker-security-disabled-detector

Detects ActiveMQ Artemis broker configuration files (`broker.xml` /
`artemis-broker.xml`) that ship with security disabled on a broker
that exposes a non-loopback acceptor.

## Why this matters

ActiveMQ Artemis is the reference Java JMS / AMQP / MQTT / STOMP
broker (the engine inside Red Hat AMQ Broker and the successor to
classic ActiveMQ "5.x"). The default `broker.xml` shipped in many
quickstart guides and Helm charts contains:

    <security-enabled>false</security-enabled>

When that broker also exposes an acceptor on `0.0.0.0` (or any
non-loopback host) on the standard ports (`61616` core, `5672` AMQP,
`1883` MQTT, `61613` STOMP), every protocol client can publish to
arbitrary addresses, drain queues, create new addresses, and call the
management API — including `forceFailover`, `destroyQueue`, and the
`org.apache.activemq.artemis:broker=...` JMX-over-management
endpoints.

LLM-generated tutorials frequently emit this combination because it is
the simplest way to make `artemis run` reachable from another
container or from a developer laptop. The detector flags that shape so
the LLM caller can intercept it before the config lands in a real
deployment.

## What it detects

For each scanned file, the detector parses the XML and reports a
finding when **all** of:

1. A `<security-enabled>` element exists with the literal text
   `false` (case-insensitive, whitespace-trimmed). XML comments are
   ignored.
2. At least one `<acceptor>` URI binds to a non-loopback host. The
   host is parsed from the URI form
   `tcp://<host>:<port>?...`. A host of `127.0.0.1`, `::1`,
   `localhost`, or the unspecified-but-explicit `127.0.0.1`-family is
   considered loopback. A bare `0.0.0.0`, `::`, public IP, hostname,
   or omitted host (which Artemis treats as "all interfaces") is
   considered public.
3. No `<security-setting match="#">` block grants the implicit
   anonymous role only the read-only subset (i.e. if security is
   disabled, the security-setting is irrelevant — it is only consulted
   when security is enabled).

If `<security-enabled>` is absent, Artemis defaults to **enabled**, so
the detector does **not** fire. Only an explicit `false` is flagged.

## CWE references

- CWE-306: Missing Authentication for Critical Function
- CWE-1188: Insecure Default Initialization of Resource
- CWE-732: Incorrect Permission Assignment for Critical Resource

## False-positive surface

- Local development brokers with every acceptor on `127.0.0.1` are
  not flagged.
- Embedded/in-VM brokers that do not declare any `<acceptor>` are not
  flagged (no network exposure to worry about).
- Suppress per file with a top-level XML comment containing
  `artemis-security-disabled-ok` (e.g.
  `<!-- artemis-security-disabled-ok: integration-test fixture -->`).

## Usage

    python3 detector.py path/to/broker.xml
    python3 detector.py examples/bad examples/good

Exit code: number of files with at least one finding (capped at 255).
Stdout format: `<file>:<line>:<reason>`.

Run `bash verify.sh` to execute the bundled good/bad fixtures.

## Verification

    $ bash verify.sh
    bad=4/4 good=0/4 PASS

(See `verify.sh` for the harness; counts adjust automatically when
fixtures are added.)
