# llm-output-spark-authenticate-false-detector

Detects Apache Spark `spark-defaults.conf` configurations that ship
`spark.authenticate = false` (the upstream default) on a deployment
that exposes the driver, executor, or standalone master ports beyond
loopback.

## Why this matters

`spark.authenticate` controls whether Spark RPC connections (driver
to executor, master to worker, client to driver) require a shared
secret. With the default `false`, anyone who can reach the RPC port
can register a fake executor, submit arbitrary serialized closures,
and execute code in the JVM of every worker — full pre-auth RCE on
the cluster. The matching `spark.network.crypto.enabled = false`
default also leaves the same RPC payload unencrypted on the wire.

LLM-generated Spark quickstarts almost always emit:

    spark.master                spark://10.0.0.5:7077
    spark.authenticate          false

because tutorials skip the secret step to keep snippets short.
This detector flags that shape so the caller can intercept it before
it reaches a cluster reachable on a routable subnet.

## What it detects

For each scanned `spark-defaults.conf`, the detector reports a
finding when:

1. The file is a Spark properties file (whitespace-separated
   `key value`, `#` comments).
2. `spark.authenticate` is unset OR explicitly `false`.
3. AND `spark.master` resolves to a non-loopback host (or is
   `yarn`/`k8s://...`/any URL whose host is not loopback), OR a
   driver/UI/blockManager bind host is set to a non-loopback address.

The reason string also notes when `spark.network.crypto.enabled` is
false (cleartext RPC), when `spark.ui.acls.enable` is false (the
Spark UI accepts kill/stage requests from anyone), and when
`spark.authenticate.secret` is present but empty.

## CWE references

- CWE-306: Missing Authentication for Critical Function
- CWE-319: Cleartext Transmission of Sensitive Information
- CWE-1188: Insecure Default Initialization of Resource

## False-positive surface

- `spark.master = local` / `local[*]` / `local[N]` is treated as a
  single-JVM dev sandbox and ignored.
- A `spark://127.0.0.1:7077` (or `localhost`, `::1`) master is
  ignored.
- A file that intentionally documents the insecure default (e.g. a
  hardening tutorial) can be suppressed with a top-of-file comment
  `# spark-auth-allowed`.

## Usage

    python3 detector.py path/to/spark-defaults.conf

Exit code: number of files with at least one finding (capped at 255).
Stdout format: `<file>:<line>:<reason>`.

Run `bash verify.sh` to execute the bundled good/bad fixtures.
