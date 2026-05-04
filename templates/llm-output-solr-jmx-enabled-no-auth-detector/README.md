# llm-output-solr-jmx-enabled-no-auth-detector

Detects Apache Solr launcher / environment files (`solr.in.sh`,
`solr.in.cmd`, related `.sh` / `.env` overrides) that turn on the
remote JMX RMI server without configuring JMX authentication.

## Why this matters

Solr ships with a single switch — `ENABLE_REMOTE_JMX_OPTS=true` —
that opens an RMI registry on `RMI_PORT` (default `18983`). When
set, the standard launcher emits these JVM flags:

```
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=<RMI_PORT>
-Dcom.sun.management.jmxremote.rmi.port=<RMI_PORT>
-Dcom.sun.management.jmxremote.local.only=false
-Dcom.sun.management.jmxremote.authenticate=false
-Dcom.sun.management.jmxremote.ssl=false
```

Without an explicit
`-Dcom.sun.management.jmxremote.authenticate=true` plus a
`jmxremote.password.file=…` (and ideally
`jmxremote.access.file=…`), anything that can reach the RMI port
can:

- Read every JMX MBean (heap stats, system properties — including
  values passed via `-D` like passwords and S3 keys, request
  metrics, Solr-internal state).
- Invoke any registered MBean operation. Historically chained into
  RCE via the `MLet` loader, `Diagnostic Command`, or arbitrary
  `MBeanServer` operations to load remote bytecode
  (CVE-2016-3427 family and JNDI-injection variants).
- Dump arbitrary serialized objects from JMX, expanding the
  Java-deserialization-gadget surface the JVM exposes.

This is a textbook CWE-306 (Missing Authentication for Critical
Function) finding. Despite that, LLM-generated Solr launcher
overrides frequently emit:

```sh
ENABLE_REMOTE_JMX_OPTS="true"
RMI_PORT="18983"
```

…with no companion `jmxremote.password.file` or
`jmxremote.authenticate=true` override anywhere in the file, and
no firewall note.

## What's checked

Per file, the detector flags when **all** of the following hold:

1. `ENABLE_REMOTE_JMX_OPTS` is set to a truthy value (`true`,
   `yes`, `1`, `on`, case-insensitive) on an uncommented line, in
   shell-style (`KEY=value`, `export KEY=value`) or Windows cmd
   style (`set KEY=value`).
2. The same file does **not** also set
   `-Dcom.sun.management.jmxremote.authenticate=true` on any
   uncommented line.
3. The same file does **not** set
   `-Dcom.sun.management.jmxremote.password.file=…` to a
   non-empty value.
4. The same file does **not** set
   `-Dcom.sun.management.jmxremote.access.file=…` to a non-empty
   value.

Comments (`#`, `//`, `REM`) are ignored when looking for both the
trigger and the companion overrides.

## Accepted (not flagged)

- `ENABLE_REMOTE_JMX_OPTS=false` (or unset / commented out).
- `ENABLE_REMOTE_JMX_OPTS=true` paired with an explicit
  `jmxremote.authenticate=true` or `jmxremote.password.file=…` or
  `jmxremote.access.file=…` override anywhere in the same file.
- Files containing the comment `# solr-jmx-no-auth-allowed`
  (intentional single-node lab fixture behind a private subnet).
- Files that don't mention `ENABLE_REMOTE_JMX_OPTS` at all.

## Refs

- CWE-306: Missing Authentication for Critical Function
- CVE-2016-3427 (Oracle JMX RMI deserialization, the canonical
  example of why anonymous JMX is dangerous)
- Apache Solr Reference Guide: "JMX with Solr"
- OWASP A07:2021 Identification and Authentication Failures

## Usage

```
python3 detector.py path/to/solr.in.sh [more.sh ...]
```

Exit code = number of flagged files (capped at 255). Findings
print as `<file>:<line>:<reason>`.
