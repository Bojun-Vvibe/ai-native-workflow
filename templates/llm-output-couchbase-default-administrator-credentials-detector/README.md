# llm-output-couchbase-default-administrator-credentials-detector

Stdlib-only Python detector that flags **Couchbase Server**
cluster-init / setup snippets that pair the default
`Administrator` cluster username with a known-weak password
(`password`, `couchbase`, `admin`, `Password1`, `changeme`, ...).

Maps to **CWE-798** (Use of Hard-coded Credentials) and
**CWE-521** (Weak Password Requirements).

## Why this matters

The Couchbase Server CLI bootstraps a cluster via
`couchbase-cli cluster-init --cluster-username Administrator
--cluster-password <pw>`. The username is fixed by every
quickstart (and by the official `couchbase/server` Docker image's
`COUCHBASE_ADMINISTRATOR_USERNAME` env), so the only secret is
the password. With a weak password, anyone who can reach port
`8091` (web UI) or `18091` (TLS) of the node can:

- read and write every bucket — i.e. all stored customer data;
- create XDCR replications to an attacker-controlled remote
  cluster, exfiltrating data continuously and silently;
- enable Eventing / Analytics services and run arbitrary JavaScript
  through `EXECUTE FUNCTION` (RCE inside the Couchbase JS sandbox);
- purge the cluster audit log to hide their tracks.

LLMs reach for `Administrator` / `password` because every "hello
world Couchbase" tutorial uses exactly that pair, and the
`couchbase/server` image's docs literally show it as the example
input to the setup wizard.

## Heuristic

We flag, outside `#` / `//` comments:

1. `couchbase-cli cluster-init ... --cluster-username Administrator
   --cluster-password <weak>` on a single line.
2. `curl ... -u Administrator:<weak> ... /pools/default` against
   the Couchbase REST setup endpoint.
3. `COUCHBASE_ADMINISTRATOR_USERNAME=Administrator` paired with
   `COUCHBASE_ADMINISTRATOR_PASSWORD=<weak>` within ~8 lines
   (Compose `environment:` blocks, `.env`, Dockerfile).
4. Helm / Operator YAML pairs of `username: Administrator` and
   `password: <weak>` within ~8 lines.

The "weak" password set is the documented quickstart defaults plus
the LLM-favourite fillers:

    password, Password1, couchbase, admin, administrator, 123456,
    changeme, default, secret

Each occurrence emits one finding line.

## What we flag

- `couchbase-cli cluster-init ... --cluster-username Administrator
  --cluster-password password` in a shell script.
- `curl -u Administrator:couchbase http://node:8091/pools/default ...`.
- A Compose `environment:` block with both
  `COUCHBASE_ADMINISTRATOR_USERNAME=Administrator` and
  `COUCHBASE_ADMINISTRATOR_PASSWORD=changeme`.
- A Helm values file with `username: Administrator` and
  `password: Password1` in the same block.

## What we accept

- `Administrator` paired with a high-entropy password
  (`--cluster-password "$(openssl rand -base64 24)"`).
- Comment-only mentions:
  `# do NOT keep --cluster-password password in production`.
- A `username: Administrator` line whose neighbouring `password:`
  reads from a `valueFrom: secretKeyRef:` block.

## CWE / standards

- **CWE-798**: Use of Hard-coded Credentials.
- **CWE-521**: Weak Password Requirements.
- Couchbase Server security hardening guide:
  > Set a strong password for the Full Administrator account
  > during initial provisioning. Do not use the example values
  > shown in the quickstart.

## Usage

```bash
python3 detect.py path/to/setup.sh
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
  01_cluster_init_cli.sh             # couchbase-cli cluster-init weak pw
  02_curl_pools_default.sh           # curl -u Administrator:couchbase ...
  03_compose_env_pair.yml            # Compose env: pair, weak pw
  04_helm_values_pair.yaml           # Helm username/password pair
examples/good/
  01_cluster_init_strong.sh          # password from openssl rand
  02_compose_env_secretref.yml       # password sourced from secret
  03_helm_values_secretref.yaml      # password via secretKeyRef
```

## Limits / known false negatives

- Programmatic builds of the CLI string from runtime variables
  (e.g. `cmd="couchbase-cli ..."; cmd+=" --cluster-password $PW"`)
  are out of scope; we only see literal substrings.
- We do not check whether port `8091` is reachable on a routable
  interface; combined with `0.0.0.0` binding, a finding here is
  critical.
- Sibling detectors in this series cover Couchbase TLS-disabled
  and unauthenticated XDCR endpoints.
