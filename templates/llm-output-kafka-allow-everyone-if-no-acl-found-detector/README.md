# llm-output-kafka-allow-everyone-if-no-acl-found-detector

Flags Apache Kafka broker configurations that set

```
allow.everyone.if.no.acl.found = true
```

This single setting tells Kafka's ACL authorizer: "if a resource has
no ACL, allow everyone to do everything to it." In any cluster where
topics are auto-created or ACLs are applied piecemeal, this collapses
the entire authorization model.

## What it catches

- Java properties (`server.properties`, `kafka.properties`):
  `allow.everyone.if.no.acl.found=true`
- YAML (Strimzi / Helm values, docker-compose):
  - `allow.everyone.if.no.acl.found: "true"`
  - `allowEveryoneIfNoAclFound: true` (camelCase variant)
  - `KAFKA_ALLOW_EVERYONE_IF_NO_ACL_FOUND: "true"` (env-key style)
- CLI / env / Dockerfile:
  - `-Dallow.everyone.if.no.acl.found=true`
  - `KAFKA_ALLOW_EVERYONE_IF_NO_ACL_FOUND=true`

## Why it's risky

Any authenticated principal — and on PLAINTEXT listeners, any
unauthenticated client — can then produce, consume, or delete any
topic, consumer group, or transactional id that simply happens to
have no explicit ACL row attached. Newly auto-created topics fall
into this category by default.

Apache / Confluent docs strongly discourage this in production. See
<https://kafka.apache.org/documentation/#security_authz>.

Maps to **CWE-732** (Incorrect Permission Assignment for Critical
Resource), **CWE-1188** (Insecure Default Initialization of
Resource), and **OWASP A05:2021** Security Misconfiguration.

## Why LLMs ship this

Tutorials and Stack Overflow answers routinely set this flag to
"fix" a `TopicAuthorizationException` that the user hits while
following along. Models suggest the same one-line fix in production
configs without flagging the blast radius.

## Usage

```bash
python3 detect.py path/to/config-or-dir
```

Exit codes:

- `0` — clean
- `1` — at least one finding (one line per finding on stdout)
- `2` — usage error

Stdlib-only, no deps. Walks directories and scans `*.properties`,
`*.conf`, `*.yaml`, `*.yml`, `*.env`, `*.sh`, `*.bash`, `*.service`,
`Dockerfile*`, `docker-compose.*`, and any file whose basename
starts with `kafka` or `server.properties`.

## Smoke test

```bash
./smoke.sh
# bad=N/N good=0/M
# PASS
```

## What it does NOT flag

- The same key set to `false` (the safe default).
- Configs that omit the key entirely (default is `false`).
- Comments / docs that mention the bad pattern.
