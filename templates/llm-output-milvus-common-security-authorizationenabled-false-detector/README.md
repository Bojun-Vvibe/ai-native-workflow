# llm-output-milvus-common-security-authorizationenabled-false-detector

Stdlib-only Python detector that flags **Milvus** vector-database
deployments that leave `common.security.authorizationEnabled` at
its upstream default of `false`, OR explicitly set it to a falsy
value (`false`, `0`, `no`, `off`).

Maps to **CWE-306** (Missing Authentication for Critical Function)
and **CWE-1188** (Insecure Default Initialization of Resource).

## Why this matters

Milvus exposes its full control plane on gRPC port 19530 and
metrics on 9091. With `authorizationEnabled: false`, every gRPC
call is unauthenticated. A caller who can reach the port can:

- enumerate every collection, partition, and index,
- read all vectors and the original payload columns,
- create, alter, or drop any collection (including dropping the
  metadata layer that backs another team's RAG application),
- insert poisoned vectors that change retrieval results for every
  downstream LLM query (a corpus-poisoning vector with no audit
  trail because no identity is bound to the call).

The upstream `milvus.yaml` shipped in `milvus-io/milvus` carries
this default, and the official quickstart docker-compose plus
the Helm chart inherit it. LLMs producing "deploy Milvus to
Kubernetes" snippets either copy the block verbatim or omit the
`security` section entirely, and the operator deploys it on a
host that is reachable from outside the cluster.

## Heuristic

We flag, outside `#` / `//` comments:

1. YAML key form: a line `authorizationEnabled: false` (or
   `False`, `0`, `no`, `off`) at any nesting level.
2. Helm CLI form: `--set ...authorizationEnabled=false`. The
   chain may contain escaped dots
   (`extraConfigFiles.user\\.yaml.common.security.authorizationEnabled`).
3. Env-var override: `MILVUS_COMMON_SECURITY_AUTHORIZATION_ENABLED=false`
   or `MILVUS_COMMON_SECURITY_AUTHORIZATIONENABLED=false`.

We suppress findings if the same file ALSO sets
`authorizationEnabled` to a truthy value somewhere — that means
the operator overrode the default upward and the falsy line is
likely a no-op or a documentation example.

## Usage

    python3 detect.py path/to/file_or_dir [more...]

Exit codes: `0` no findings, `1` findings, `2` usage error.

## Verified worked example

The `examples/` tree contains 4 bad fixtures (milvus.yaml,
helm values, helm-install shell, env-file) and 3 good fixtures
(authorization explicitly enabled in milvus.yaml, helm values,
and env-file). Run:

    bash smoke.sh

Expected output:

    bad=4/4 good=0/3
    PASS

## Remediation

- Set `common.security.authorizationEnabled: true` in
  `milvus.yaml` for any deployment that is reachable beyond a
  trusted localhost or a tightly-firewalled private subnet.
- Create a non-default root user with a strong password and
  bind every client (pymilvus, MilvusDM, Attu) to that user.
- Rotate the default `root` / `Milvus` credentials immediately
  after enabling authorization.
- Layer a network-level control (NetworkPolicy, security group)
  in addition to authorization — defense in depth.

## Mapping

- CWE-306 — Missing Authentication for Critical Function.
- CWE-1188 — Insecure Default Initialization of Resource.
