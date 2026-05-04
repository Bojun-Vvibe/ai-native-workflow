# llm-output-hive-server2-authentication-none-detector

Detects Apache Hive `hive-site.xml` configurations that ship
HiveServer2 (HS2) with `hive.server2.authentication = NONE` while
bound to a non-loopback host.

## Why this matters

`NONE` is the upstream default for `hive.server2.authentication`. With
that value, HS2 accepts any user string supplied by the JDBC/ODBC
client and — when `hive.server2.enable.doAs=true` (also the default)
— runs the resulting queries on HDFS as that supplied user. A network
attacker who can reach the Thrift port can therefore impersonate any
account, including `hdfs` or `hive`, and read or destroy every table
and warehouse directory in the cluster.

LLM-generated Hadoop-stack tutorials almost always emit:

    <property>
      <name>hive.server2.authentication</name>
      <value>NONE</value>
    </property>

because it is the path of least resistance to a working
`beeline -u jdbc:hive2://host:10000`. The detector flags that shape so
the caller can intercept it before it lands in a real cluster.

## What it detects

For each scanned `hive-site.xml`, the detector reports a finding when:

1. The XML root is `<configuration>`.
2. `hive.server2.authentication` is explicitly set to `NONE`
   (case-insensitive).
3. `hive.server2.thrift.bind.host` is unset OR set to a non-loopback
   address.

The reason string also notes when SSL is off, when `doAs` is enabled
(amplifying the impact), and when `hive.security.authorization` is
not enabled.

## CWE references

- CWE-287: Improper Authentication
- CWE-306: Missing Authentication for Critical Function
- CWE-1188: Insecure Default Initialization of Resource

## False-positive surface

- `hive.server2.thrift.bind.host = 127.0.0.1` (or `localhost`,
  `::1`) is treated as a dev sandbox and ignored.
- A file that intentionally documents `NONE` (e.g. an example for a
  hardening tutorial) can be suppressed with a top-of-file XML comment
  `<!-- hive-auth-allowed -->`.

## Usage

    python3 detector.py path/to/hive-site.xml

Exit code: number of files with at least one finding (capped at 255).
Stdout format: `<file>:<line>:<reason>`.

Run `bash verify.sh` to execute the bundled good/bad fixtures.
