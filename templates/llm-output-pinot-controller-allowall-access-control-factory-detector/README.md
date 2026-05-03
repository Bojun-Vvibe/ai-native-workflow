# llm-output-pinot-controller-allowall-access-control-factory-detector

Flags Apache Pinot controller / broker configurations that wire
the access-control factory to `AllowAllAccessControlFactory` —
the upstream "no checks at all" stub that ships with Pinot for
development and that LLMs repeatedly emit as a "make auth work"
answer.

## Upstream

- `apache/pinot` — https://github.com/apache/pinot
- Source of the stub:
  `pinot-controller/src/main/java/org/apache/pinot/controller/api/access/AllowAllAccessControlFactory.java`
- Pinot security doc:
  https://docs.pinot.apache.org/operators/tutorials/authentication
- Verified against Pinot 1.0.0 .. 1.2.x where
  `AllowAllAccessControlFactory` is still the documented "open"
  factory and the default when the property is unset.

## What it detects

All gated by an in-file Pinot context token (any of: `pinot`,
`apache.pinot`, `org.apache.pinot`, `pinot-controller`,
`pinot-broker`, `pinot-server`):

1. `controller.admin.access.control.factory.class = …AllowAllAccessControlFactory`
   in a `.properties` / `.conf` file.
2. `pinot.broker.access.control.class = …AllowAllAccessControlFactory`.
3. Helm / k8s values: `accessControlFactory: AllowAll` (or
   `factory: AllowAllAccessControlFactory`) under a Pinot chart.
4. JVM start-script flag
   `-Dcontroller.admin.access.control.factory.class=…AllowAllAccessControlFactory`.

## Why this is dangerous

Pinot's controller exposes the cluster admin REST surface
(`/tables`, `/segments`, `/schemas`, `/instances`, `/tenants`,
`/tasks`). With `AllowAllAccessControlFactory` every endpoint
returns "authorized" without consulting any credential. Any
unauthenticated network reachability becomes:

- arbitrary table / schema deletion → data loss;
- arbitrary segment upload → data poisoning of every Pinot
  query that reads the table;
- task scheduling (`MinionTask`) of attacker-defined task
  classes → remote code execution on minion workers;
- exfiltration of segment data via download endpoints.

The class is named, source-visible, and documented as a
development-only stub; shipping it to production removes the
authentication boundary on the cluster admin plane.

## CWE / OWASP refs

- **CWE-284**: Improper Access Control
- **CWE-285**: Improper Authorization
- **CWE-306**: Missing Authentication for Critical Function
- **CWE-1188**: Insecure Default Initialization of Resource
- **CWE-732**: Incorrect Permission Assignment for Critical Resource
- **OWASP A01:2021** — Broken Access Control
- **OWASP A05:2021** — Security Misconfiguration

## False positives

Skipped:

- Files with no Pinot context (an unrelated Java class also
  named `AllowAllAccessControlFactory` in a different project).
- Comment-only mentions of the stub in docs.
- Configs that wire a real factory such as
  `BasicAuthAccessControlFactory` or
  `ZkBasicAuthAccessControlFactory`.

## Run

```
python3 detect.py path/to/file-or-dir [more...]
```

Exit codes: `0` clean, `1` findings, `2` usage error.

## Worked example

```
$ ./smoke.sh
bad=4/4 good=0/3
PASS
```

Four `examples/bad/` files (a `controller.conf` setting
`controller.admin.access.control.factory.class` to the AllowAll
class, a `broker.conf` doing the equivalent for the broker, a
Helm `values.yaml` with `accessControlFactory: AllowAll`, and a
`start-controller.sh` passing the AllowAll class as a `-D` JVM
flag) each trip the detector. Three `examples/good/` files (a
`controller.conf` wired to `BasicAuthAccessControlFactory`, a
Helm `values.yaml` wired to `ZkBasicAuthAccessControlFactory`,
and a `start-controller.sh` that pulls the factory class name
from `$PINOT_AUTH_FACTORY`) all stay clean.
