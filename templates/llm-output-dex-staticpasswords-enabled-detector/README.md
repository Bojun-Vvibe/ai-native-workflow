# llm-output-dex-staticpasswords-enabled-detector

Stdlib-only Python detector that flags **Dex**
(https://github.com/dexidp/dex) configurations that enable the
local **static-password** identity backend in production-shaped
deployments, or that copy the well-known **tutorial credentials**
(`admin@example.com` / bcrypt hash for the literal word
`password`) verbatim.

Maps to **CWE-798** (use of hard-coded credentials), **CWE-1392**
(use of default credentials), and **CWE-287** (improper
authentication).

## Why this matters

Dex is an OIDC identity broker. The recommended production path
is to federate to a real upstream IdP (LDAP, GitHub, OIDC, SAML,
…) and leave `enablePasswordDB: false`. The `staticPasswords:`
block exists for `getting started` only.

The Dex docs ship this exact entry as an example:

```yaml
staticPasswords:
- email: "admin@example.com"
  hash: "$2a$10$33EMT0cVYVlPy6WAMCLsceLYjWhuHpbz5yuZxu/GAFj03J9Lytjuy"
  username: "admin"
  userID: "08a8684b-db88-4b73-90a9-3cd1661f5466"
```

That hash is bcrypt of the literal word `password`. LLMs frequently
copy it verbatim into Helm values or k8s ConfigMaps and also flip
`enablePasswordDB: true`, producing a public OIDC issuer with a
well-known credential.

Upstream reference:

- <https://github.com/dexidp/dex>
- <https://dexidp.io/docs/connectors/local/>

## Heuristic

A file is "dex-related" if it mentions one of:
- image `quay.io/dexidp/dex` / `ghcr.io/dexidp/dex` / `dexidp/dex`
- the keys `enablePasswordDB`, `staticPasswords`, `staticClients`

…**and** the file contains a config-shaped key (`issuer:`,
`connectors:`, `storage:`, `staticClients:`, `staticPasswords:`),
which keeps unrelated docs from triggering on the word "dex".

Inside such a file, outside `#` / `//` comments, we flag:

1. `enablePasswordDB: true` (any indentation).
2. A `staticPasswords:` block whose entries use the demo email
   `admin@example.com`.
3. A `staticPasswords:` block that contains the canonical Dex
   tutorial bcrypt hash
   `$2a$10$33EMT0cVYVlPy6WAMCLsce...` (hash of `password`).
4. As a fallback, `staticPasswords:` together with
   `enablePasswordDB: true` in the same file even if the entries
   look custom.

Each occurrence emits one finding line.

## What we accept (no false positive)

- `enablePasswordDB: false` with corp LDAP / GitHub / OIDC
  connector.
- README / runbook that mentions the bad shape inside `#` /
  `//` comments only.
- A non-dex YAML that happens to mention "dex" in passing.

## What we flag

- Helm values with `enablePasswordDB: true` and a custom hash.
- k8s ConfigMap embedding `config.yaml` with
  `enablePasswordDB: true`.
- Any file with the canonical
  `$2a$10$33EMT0cVYVlPy6WAMCLsce...` tutorial hash inside a
  `staticPasswords:` block.
- Any `staticPasswords:` entry with `email: admin@example.com`.

## Limits / known false negatives

- We do not parse YAML into a tree; we operate line-by-line. A
  block split across two ConfigMaps in the same file is fine; a
  block whose `staticPasswords:` header was emitted by a Helm
  template fragment may be missed.
- We do not crack bcrypt hashes; we only match the exact
  tutorial-prefix pattern.
- We do not enforce policy on `staticClients:` (separate concern).

## Usage

```bash
python3 detect.py path/to/repo/
python3 detect.py dex.yaml values.yaml
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
  01_demo_creds_dex.yaml          # admin@example.com + tutorial hash
  02_helm_values_enable_true.yaml # enablePasswordDB: true (custom hash)
  03_k8s_configmap.yaml           # ConfigMap embeds enablePasswordDB:true
  04_demo_hash_only.yaml          # custom email but tutorial hash
examples/good/
  01_federated_no_password_db.yaml # OIDC connector, enablePasswordDB:false
  02_helm_ldap_only.yaml           # LDAP connector, enablePasswordDB:false
  03_runbook_comment_only.yaml     # bad form in comments only
```
