# llm-output-hasura-graphql-no-admin-secret-detector

Stdlib-only Python detector that flags **Hasura GraphQL Engine**
deployments that ship without `HASURA_GRAPHQL_ADMIN_SECRET`. Maps to
**CWE-306** (missing authentication for critical function),
**CWE-1188** (insecure default initialization of resource), and
**CWE-284** (improper access control).

When `HASURA_GRAPHQL_ADMIN_SECRET` is unset, Hasura serves the entire
GraphQL admin surface, including the Console, the metadata API, the
schema/run-sql endpoint, and unrestricted access to every tracked
table — to anyone who can reach the listening port. Because Hasura
also exposes `/v2/query` with `run_sql`, an unauthenticated reachable
instance is functionally equivalent to a public superuser shell on the
backing Postgres database.

## Heuristic

We flag any of the following, outside `#` / `//` comment lines:

1. Docker `-e HASURA_GRAPHQL_ENABLE_CONSOLE=true` (or `=1`) on a
   `hasura/graphql-engine` image with **no** matching
   `HASURA_GRAPHQL_ADMIN_SECRET` env var anywhere in the same file.
2. docker-compose `image: hasura/graphql-engine[:tag]` services whose
   `environment:` block sets `HASURA_GRAPHQL_ENABLE_CONSOLE: "true"`
   and omits `HASURA_GRAPHQL_ADMIN_SECRET`.
3. Kubernetes manifests (`kind: Deployment` / `Pod`) that reference
   `hasura/graphql-engine` and do not list an env entry named
   `HASURA_GRAPHQL_ADMIN_SECRET` (neither `value:` nor `valueFrom:`).
4. `.env` / shell exports that set `HASURA_GRAPHQL_ADMIN_SECRET=` to
   the empty string, `""`, `''`, or the placeholder `changeme`.

Each occurrence emits one finding line.

## CWE / standards

- **CWE-306**: Missing Authentication for Critical Function.
- **CWE-1188**: Insecure Default Initialization of Resource.
- **CWE-284**: Improper Access Control.
- Hasura docs: "In production deployments, you must configure an
  admin secret to prevent unauthorized access to your GraphQL API."

## What we accept (no false positive)

- A `HASURA_GRAPHQL_ADMIN_SECRET` env var sourced from
  `valueFrom.secretKeyRef` or set to a non-empty literal.
- Files that mention the variable in commentary / documentation.
- docker-compose services using a non-Hasura image even if
  `HASURA_GRAPHQL_ENABLE_CONSOLE` is set elsewhere.

## Layout

```
detect.py            stdlib-only scanner
smoke.sh             runs detect.py against examples/ and asserts
examples/bad/        4 fixtures that MUST be flagged
examples/good/       3 fixtures that MUST NOT be flagged
```

## Run

```
python3 detect.py path/to/docker-compose.yml
python3 detect.py path/to/repo
bash smoke.sh
```

Exit codes: `0` = clean, `1` = findings, `2` = usage error.

## Why this is a real LLM failure mode

Most LLM-generated "deploy Hasura locally" snippets enable the Console
to make the developer experience smooth, but elide the admin secret
because the same snippet will then refuse to render the Console
without prompting for one. Developers copy the snippet into a
`docker-compose.prod.yml` and ship it with `-p 8080:8080` exposed.
This detector catches that paste before it reaches a public IP.
