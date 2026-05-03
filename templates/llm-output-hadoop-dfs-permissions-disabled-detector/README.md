# llm-output-hadoop-dfs-permissions-disabled-detector

Stdlib-only Python detector that flags **Hadoop HDFS** configurations
which disable filesystem permission checks — i.e.
`dfs.permissions.enabled` set to `false` (or the legacy alias
`dfs.permissions`) in `hdfs-site.xml`, in a `core-site.xml` override,
or as a `-D` flag on a `hdfs`/`hadoop` command line.

When `dfs.permissions.enabled=false`, the NameNode stops enforcing
POSIX-style owner/group/mode checks on every HDFS path. Any client
that can reach the NameNode RPC port (default 8020 / 9000) can read,
overwrite, or delete every file in the cluster regardless of its
declared owner — the metadata is still recorded, but never consulted
on access.

Maps to:
- **CWE-732**: Incorrect Permission Assignment for Critical Resource.
- **CWE-285**: Improper Authorization.
- **CWE-1188**: Insecure Default Initialization of Resource.

## Heuristic

We flag any of the following, outside `<!-- ... -->` XML comments
and outside `#` shell comment lines:

1. An XML `<property>` block in an `*-site.xml` whose `<name>` is
   `dfs.permissions.enabled` (or the deprecated alias
   `dfs.permissions`) and whose `<value>` is `false` / `0` / `no`
   (case-insensitive, whitespace-tolerant).
2. A `-Ddfs.permissions.enabled=false` (or the legacy
   `-Ddfs.permissions=false`) on a `hdfs`, `hadoop`, `yarn`, or
   `mapred` command line in a shell script, Dockerfile,
   docker-compose `command:`, systemd `ExecStart=`, or k8s
   container args list.
3. The same key set to a falsy value in a `.properties` /
   `.conf` / `.env` style key=value file when the surrounding
   file looks like a Hadoop config (presence of other `dfs.*`
   or `fs.defaultFS` keys, or a `hadoop` / `hdfs` token).

Each occurrence emits one finding line.

## CWE / standards

- **CWE-732**: Incorrect Permission Assignment for Critical Resource.
- **CWE-285**: Improper Authorization.
- **CWE-1188**: Insecure Default Initialization of Resource.
- Apache Hadoop `hdfs-default.xml`, `dfs.permissions.enabled`:
  "If `true`, enable permission checking in HDFS. If `false`,
  permission checking is turned off, but all other behavior is
  unchanged. Switching from one parameter value to the other does
  not change the mode, owner or group of files or directories."

## What we accept (no false positive)

- `dfs.permissions.enabled` set to `true` (the secure default).
- An XML comment that mentions the key:
  `<!-- dfs.permissions.enabled=false is unsafe -->`.
- A shell comment: `# do NOT set dfs.permissions.enabled=false`.
- Other `dfs.*` keys (`dfs.replication`, `dfs.blocksize`, etc.).
- A `dfs.permissions.superusergroup` key (a different setting
  that names the supergroup; it does not disable checks).

## Layout

```
detect.py            stdlib-only scanner (regex over text)
smoke.sh             runs detect.py against examples/ and asserts
examples/bad/        4 fixtures that MUST be flagged
examples/good/       3 fixtures that MUST NOT be flagged
```

## Run

```
python3 detect.py path/to/hdfs-site.xml
python3 detect.py path/to/repo
bash smoke.sh
```

Exit codes: `0` = clean, `1` = findings, `2` = usage error.

## Why this is a real LLM failure mode

Every "I get `Permission denied: user=root, access=WRITE,
inode=...`" question on Stack Overflow has at least one answer
that recommends adding `<property><name>dfs.permissions.enabled
</name><value>false</value></property>` to `hdfs-site.xml`. It
"fixes" the error by removing all access control, and LLMs that
have ingested those answers reproduce the snippet verbatim.
The detector exists to catch the paste before it reaches a
production `hdfs-site.xml`, a Helm values file, or a Hadoop
container image build.
