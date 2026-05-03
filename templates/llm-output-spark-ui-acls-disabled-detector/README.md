# llm-output-spark-ui-acls-disabled-detector

Stdlib-only Python detector that flags **Apache Spark** configurations
that disable the Web UI access control list (ACL) gate, or that
wildcard-grant `modify` / `admin` ACLs to every user.

Maps to **CWE-284** (Improper Access Control), **CWE-306** (Missing
Authentication for Critical Function), and **CWE-732** (Incorrect
Permission Assignment for Critical Resource).

## Why this matters

Spark's Web UI (driver port 4040, history server port 18080) exposes:

- the full SQL plan + parameters of every query — literals inlined
  in queries (including any password accidentally hardcoded in a
  JDBC URL) appear here in plaintext;
- the environment tab including `spark.*.password` /
  `spark.hadoop.*` values (Spark redacts only keys matching its
  redaction regex; custom keys leak);
- thread dumps with stack frames containing argument values;
- `kill` links that terminate running stages and jobs.

`spark.acls.enable` (and the older alias `spark.ui.acls.enable`)
gate all of the above. When set to `false` and the UI is reachable
on a routable interface, anyone who can hit port 4040 / 18080 can
read job parameters and kill running jobs.

`spark.modify.acls=*` and `spark.admin.acls=*` grant the same
surface to every authenticated user (or every user, when auth is
also off — see sibling detectors).

LLMs reach for `spark.acls.enable=false` because every "make the
Spark UI work behind my reverse proxy" Stack Overflow answer turns
ACLs off instead of configuring the proxy correctly.

## Heuristic

We flag, outside `#` / `//` comments:

1. `spark.acls.enable` set to a falsy value
   (`false`, `False`, `0`, `no`, `off`).
2. `spark.ui.acls.enable` (legacy alias) set to a falsy value.
3. `spark.modify.acls` whose value is exactly `*`.
4. `spark.admin.acls`  whose value is exactly `*`.
5. CLI form: `--conf spark.acls.enable=false`.
6. Programmatic form: `.set("spark.acls.enable", "false")` or
   PySpark builder `.config("spark.acls.enable", "false")` (also
   covers `setIfMissing`).

Each occurrence emits one finding line.

## What we flag

- `spark.acls.enable false` in `spark-defaults.conf`.
- `--conf spark.ui.acls.enable=false` in a `spark-submit` wrapper.
- `.config("spark.acls.enable", "false")` in PySpark.
- `spark.modify.acls *` / `spark.admin.acls *` (wildcard grant).

## What we accept

- `spark.acls.enable true` with `spark.admin.acls ops-team`.
- Comment-only mentions: `# do NOT set spark.acls.enable=false`.
- Named-group ACLs like `spark.modify.acls etl-svc`.

## CWE / standards

- **CWE-284**: Improper Access Control.
- **CWE-306**: Missing Authentication for Critical Function.
- **CWE-732**: Incorrect Permission Assignment for Critical
  Resource.
- Apache Spark security docs: "If your applications are using event
  logging, the directory where the event logs go must be manually
  created and have proper permissions set on it." and "ACLs control
  who has access to view and modify a Spark application."

## Usage

```bash
python3 detect.py path/to/spark-defaults.conf
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
  01_spark_defaults_acls_off.conf       # spark.acls.enable false
  02_spark_submit_legacy_alias.sh       # --conf spark.ui.acls.enable=false
  03_pyspark_set_false.py               # .config(..., "false")
  04_history_server_wildcard_acls.conf  # spark.modify.acls *
examples/good/
  01_spark_defaults_acls_on.conf        # acls on, admins pinned
  02_spark_submit_pinned_acls.sh        # named group acls
  03_pyspark_acls_on_with_warning.py    # acls on, warning in comment
```

## Limits / known false negatives

- Programmatic configuration that builds the key from a runtime
  string (e.g. `spark.set(prefix + "acls.enable", flag)`) is out
  of scope.
- We do not cross-check that the UI is actually reachable on a
  routable interface; combined with `spark.ui.bindAddress=0.0.0.0`
  and no reverse-proxy auth, this finding becomes critical.
- Sibling detectors in this series cover Spark event-log directory
  permissions and `spark.authenticate=false`.
