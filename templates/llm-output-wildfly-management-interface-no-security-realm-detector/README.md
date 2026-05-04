# llm-output-wildfly-management-interface-no-security-realm-detector

Detects WildFly / JBoss EAP `standalone.xml` (and `domain.xml` /
`host.xml`) configurations whose `<management-interfaces>` block
exposes the HTTP or native management interface on a non-loopback
address with **no `security-realm` attribute**. That combination
makes the WildFly CLI / HAL console reachable from the network with
no authentication at all.

## Why this matters

WildFly (and Red Hat JBoss EAP) ship with a `<management>` subsystem
that hosts:

- the `/management` REST API used by `jboss-cli.sh`,
- the HAL web console at `/console`,
- and the native management protocol on port `9999` / `9990`.

Any caller who can reach the management interface **and** is not
gated by a `security-realm` can `deploy` arbitrary `.war` /
`.jar` artefacts, read every system property, dump credentials from
the vault, or execute arbitrary OS commands via the
`jboss-as-cli` `exec-command` op. This is one of the most-exploited
JBoss / WildFly CVE classes (e.g. JBoss "Invoker" exposure, the
JMXInvokerServlet family, and the unauthenticated JBoss CLI RCEs).

The default ships with `inet-address` bound to `127.0.0.1` and
`security-realm="ManagementRealm"`. LLM-generated quickstart guides
often emit:

    <interface name="management">
      <inet-address value="${jboss.bind.address.management:0.0.0.0}"/>
    </interface>

    <management-interfaces>
      <http-interface http-authentication-factory="..." />  <!-- removed -->
      <http-interface>                                       <!-- no realm! -->
        <socket-binding http="management-http"/>
      </http-interface>
    </management-interfaces>

so the console is reachable from anywhere on the network with no
auth. The detector flags that shape so the LLM caller can intercept
it before the config lands in a real deployment.

## What it detects

For each scanned XML file, the detector reports a finding when **all**
of:

1. The `management` interface (interface element with `name="management"`)
   has an `<inet-address>` whose `value` resolves to a non-loopback
   host. Property-style values like `${jboss.bind.address.management:X}`
   are evaluated against the literal default `X`.
2. The file contains a `<management-interfaces>` block with at least
   one of `<http-interface>` or `<native-interface>` that has
   **none** of the following attributes set to a non-empty value:
   `security-realm`, `http-authentication-factory`,
   `sasl-authentication-factory`, `http-upgrade` with `sasl-authentication-factory`.

Files without a `<management-interfaces>` block are not flagged
(nothing is exposed). Files that bind only to loopback are not
flagged regardless of realm config.

## CWE references

- CWE-306: Missing Authentication for Critical Function
- CWE-284: Improper Access Control
- CWE-1188: Insecure Default Initialization of Resource

## False-positive surface

- Domain controllers configured behind a hardened bastion are still
  flagged — that's intentional. Use the suppression comment if the
  network controls are enforced elsewhere (e.g. mTLS-only ingress).
- Suppress per file with a top-level XML comment containing
  `wildfly-mgmt-no-realm-ok`.

## Usage

    python3 detector.py path/to/standalone.xml
    python3 detector.py examples/bad examples/good

Exit code: number of files with at least one finding (capped at 255).
Stdout format: `<file>:<line>:<reason>`.

Run `bash verify.sh` to execute the bundled good/bad fixtures.

## Verification

    $ bash verify.sh
    bad=4/4 good=0/4 PASS
