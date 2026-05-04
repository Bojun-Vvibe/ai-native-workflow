# llm-output-strimzi-kafka-listener-no-auth-detector

Detects Strimzi `Kafka` custom-resource manifests where an externally
exposed listener (`type: route` / `loadbalancer` / `nodeport` /
`ingress`) is declared without an `authentication:` block.

## Why this matters

Strimzi listeners under `spec.kafka.listeners` default to **no
authentication** when the `authentication` field is omitted. For
listeners of `type: internal` that may be acceptable inside a cluster
network policy, but for listeners that route through OpenShift Routes,
LoadBalancer Services, NodePorts, or Ingress, the broker becomes
reachable from outside the cluster and any client that completes the
TCP / TLS handshake can produce / consume to every topic.

LLM-generated quickstart manifests routinely emit:

    listeners:
      - name: external
        port: 9094
        type: route
        tls: true

with no `authentication:` line, because the upstream Strimzi
"hello-world" example uses exactly that shape. This detector flags
that pattern.

## What it detects

For each YAML file with `kind: Kafka`, the detector walks each entry
in `spec.kafka.listeners` and reports a finding when **all** of:

1. `type` is one of `route`, `loadbalancer`, `nodeport`, `ingress`.
2. The list item contains no `authentication:` field anywhere in its
   block.

Listeners with `type: internal` (or `cluster-ip`) are ignored. The
check is structural (indent-aware) and supports the common Strimzi
list-of-listeners shape.

## CWE references

- CWE-306: Missing Authentication for Critical Function
- CWE-284: Improper Access Control
- CWE-862: Missing Authorization

## False-positive surface

- Sandboxes / dev clusters intentionally open: suppress per file with
  a top comment `# strimzi-listener-noauth-allowed`.
- The detector only triggers for `kind: Kafka`. Other Strimzi CRDs
  (`KafkaTopic`, `KafkaUser`) are unaffected.
- Multi-document YAML: if any document is `kind: Kafka`, that document
  is scanned; non-Kafka documents are skipped.

## Usage

    python3 detector.py path/to/kafka.yaml

Exit code: number of files with at least one finding (capped at 255).
Stdout format: `<file>:<line>:<reason>`.

Run `bash verify.sh` to execute the bundled good/bad fixtures.

## Worked example

Live run against the bundled fixtures:

    $ bash verify.sh
    bad=4/4 good=0/3
    PASS

Per-fixture output:

    $ python3 detector.py examples/bad/route-noauth.yaml
    examples/bad/route-noauth.yaml:9:Strimzi Kafka listener name=external type=route is exposed externally with no authentication block
    $ python3 detector.py examples/bad/loadbalancer-noauth.yaml
    examples/bad/loadbalancer-noauth.yaml:9:Strimzi Kafka listener name=lb type=loadbalancer is exposed externally with no authentication block
    $ python3 detector.py examples/bad/nodeport-noauth.yaml
    examples/bad/nodeport-noauth.yaml:15:Strimzi Kafka listener name=nodeport-ext type=nodeport is exposed externally with no authentication block
    $ python3 detector.py examples/bad/ingress-noauth.yaml
    examples/bad/ingress-noauth.yaml:9:Strimzi Kafka listener name=ingress type=ingress is exposed externally with no authentication block

Good fixtures all return exit code 0 and emit no lines.
