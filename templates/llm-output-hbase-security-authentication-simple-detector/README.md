# llm-output-hbase-security-authentication-simple-detector

Detects Apache HBase `hbase-site.xml` configurations that ship with
`hbase.security.authentication = simple` (the insecure default) on a
cluster that is not loopback-only.

## Why this matters

`simple` authentication trusts whatever username the client process
presents over the HBase RPC. Combined with the default
`hbase.security.authorization = false`, any TCP client that can reach
the HMaster or RegionServer port can read and mutate every region as
any user — including the HBase superuser. The corresponding hardened
posture is `hbase.security.authentication = kerberos` plus
`hbase.security.authorization = true` and `hbase.rpc.protection`
raised to `integrity` or `privacy`.

LLM-generated quickstart configs commonly include the shape:

    <property>
      <name>hbase.security.authentication</name>
      <value>simple</value>
    </property>

because it matches the upstream "getting started" docs. The detector
flags that shape so the caller can intercept it before it lands in a
real cluster.

## What it detects

For each scanned `hbase-site.xml`, the detector reports a finding when:

1. The XML root is `<configuration>`.
2. `hbase.security.authentication` is explicitly set to `simple`.
3. The cluster is not loopback-only — that is, neither
   `hbase.master.ipc.address` nor `hbase.regionserver.ipc.address` is
   one of `127.0.0.1` / `::1` / `localhost`, AND the configuration is
   not `hbase.cluster.distributed=false` with a loopback-only
   `hbase.zookeeper.quorum`.

The reason string also notes when `hbase.security.authorization` is
not `true` and when `hbase.rpc.protection` is unset or only
`authentication`.

## CWE references

- CWE-287: Improper Authentication
- CWE-1188: Insecure Default Initialization of Resource
- CWE-306: Missing Authentication for Critical Function

## False-positive surface

- Standalone / pseudo-distributed dev sandboxes bound to loopback are
  not flagged.
- A file that intentionally documents `simple` (e.g. an example for a
  hardening tutorial) can be suppressed with a top-of-file XML comment
  `<!-- hbase-auth-allowed -->`.

## Usage

    python3 detector.py path/to/hbase-site.xml

Exit code: number of files with at least one finding (capped at 255).
Stdout format: `<file>:<line>:<reason>`.

Run `bash verify.sh` to execute the bundled good/bad fixtures.
