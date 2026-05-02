# llm-output-cassandra-allowall-authenticator-detector

Detect Apache Cassandra `cassandra.yaml` snippets (or rendered docs) that
leave authentication or authorization fully open via the `AllowAll*` family
of plugins. These are Cassandra's *defaults*, and LLMs frequently parrot
the default config when asked "how do I get a Cassandra cluster running" —
which produces a cluster where any client that can reach port 9042 can
read or modify every keyspace.

## What this catches

| Rule | Pattern | Why it matters |
|------|---------|----------------|
| 1 | `authenticator: AllowAllAuthenticator` | No login required at all |
| 2 | `authorizer: AllowAllAuthorizer` | Every authenticated user has every permission |
| 3 | `role_manager: AllowAllRoleManager` | `GRANT` / `REVOKE` are no-ops |
| 4 | `internode_encryption: none` plus any `AllowAll*` line | Cluster is both unauthenticated and in plaintext on the wire |

The detector deliberately ignores commented-out `# authenticator: AllowAll...`
lines so that documentation that *warns* against the insecure default does
not trigger.

## What bad LLM output looks like

```
authenticator: AllowAllAuthenticator
authorizer: CassandraAuthorizer
listen_address: 10.0.0.5
rpc_address: 0.0.0.0
```

```
authenticator: PasswordAuthenticator
authorizer: AllowAllAuthorizer
```

## What good LLM output looks like

```
authenticator: PasswordAuthenticator
authorizer: CassandraAuthorizer
role_manager: CassandraRoleManager
internode_encryption: all
```

## Sample layout

```
samples/
  bad/   # ≥3 files; every file MUST be flagged
  good/  # ≥3 files; no file may be flagged
```

## Run the smoke test

```sh
bash detect.sh samples/bad/* samples/good/*
```

The script exits `0` only when every `bad/*` is flagged and no `good/*` is.

## Verification

```
$ bash detect.sh samples/bad/* samples/good/*
BAD  samples/bad/01-allowall-authenticator.yaml
BAD  samples/bad/02-allowall-authorizer.yaml
BAD  samples/bad/03-allowall-role-manager.yaml
BAD  samples/bad/04-no-encryption-no-auth.yaml
GOOD samples/good/01-password-auth.yaml
GOOD samples/good/02-commented-warning.yaml
GOOD samples/good/03-mtls-everywhere.yaml
bad=4/4 good=0/3 PASS
```

## Recommended fix when this fires

Switch to `PasswordAuthenticator` + `CassandraAuthorizer` + `CassandraRoleManager`,
create a real superuser, drop the default `cassandra/cassandra` account, and
enable `internode_encryption: all` plus client TLS with `require_client_auth: true`.
