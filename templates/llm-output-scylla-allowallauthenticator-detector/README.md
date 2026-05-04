# llm-output-scylla-allowallauthenticator-detector

Detect ScyllaDB configuration snippets emitted by LLMs that leave the
cluster wide-open via the `AllowAll*` authenticator/authorizer family.

## Why it matters

ScyllaDB is wire-compatible with Apache Cassandra and ships the same
insecure defaults:

```yaml
authenticator: AllowAllAuthenticator   # default - no auth
authorizer:    AllowAllAuthorizer      # default - no perms
```

When asked "give me a `scylla.yaml`" or "deploy Scylla on Kubernetes",
LLMs reproduce these defaults verbatim. Combined with the typical
`broadcast_rpc_address: 0.0.0.0` an LLM also emits to "make it
reachable", the resulting cluster lets any client that can hit port
9042 read or modify every keyspace.

## Rules

| # | Pattern | Why it matters |
|---|---------|----------------|
| 1 | `authenticator: AllowAllAuthenticator` (also `--authenticator=...`, `SCYLLA_AUTHENTICATOR=...`) | No login required at all |
| 2 | `authorizer: AllowAllAuthorizer` (same variants) | Every authenticated user has every permission |
| 3 | Any `AllowAll*` rule above + non-loopback `broadcast_rpc_address` / `rpc_address` / `listen_address` / `broadcast_address` | Cluster is reachable from anywhere with no auth |

The detector strips `#` comments before matching, so a doc that
*warns* against the insecure default (`# never set authenticator: AllowAllAuthenticator`)
does not trigger.

## Suppression

Add `# scylla-public-readonly-ok` anywhere in the file to disable all
rules (intentional public sandbox / lab cluster).

## Usage

```bash
# Single file
python3 detector.py path/to/scylla.yaml

# Many files - exit code = number of files with findings
python3 detector.py manifests/*.yaml

# stdin
helm template scylla/scylla | python3 detector.py
```

Output format:

```
manifests/scylla.yaml:14: authenticator set to AllowAllAuthenticator (no login required)
manifests/scylla.yaml:15: authorizer set to AllowAllAuthorizer (every user has every permission)
manifests/scylla.yaml:8: non-loopback bind '0.0.0.0' combined with AllowAll* auth - cluster is open to network
```

## Tests

```bash
bash test.sh
# or
python3 test.py
```

Both run the detector against `examples/bad/*` (must all flag) and
`examples/good/*` (must all pass clean), printing
`PASS bad=4/4 good=0/3` on success.
