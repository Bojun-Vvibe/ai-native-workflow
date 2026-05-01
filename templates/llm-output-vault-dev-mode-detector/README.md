# llm-output-vault-dev-mode-detector

Stdlib-only Python detector that flags **HashiCorp Vault** deployments
running the server in `-dev` mode. Maps to **CWE-798** (use of
hard-coded credentials), **CWE-1188** (insecure default
initialization), and **CWE-256/257** (recoverable storage of
credentials).

`vault server -dev`:

- stores everything in-memory (data is lost on restart),
- starts unsealed with a single root token printed to the log,
- disables TLS by default,
- is documented by HashiCorp as **"ONLY for development"**.

When this slips into a Dockerfile, docker-compose stack, Helm chart,
Kubernetes manifest, systemd unit, or shell script that the team
actually deploys, every secret handed to the cluster lives in RAM
behind a fixed, well-known root token. That is a credential-store
bypass, not a "dev convenience".

LLMs reach for `vault server -dev` because every "5-minute Vault
tutorial" on the internet uses it, and because production setup
(seal, storage backend, TLS, audit) is multi-page.

## Heuristic

We flag any of the following, outside `#` / `//` comments:

1. `vault server -dev` (and `--dev`, `-dev-root-token-id=...`,
   `-dev-listen-address=...`).
2. Exec-array form: `["vault","server","-dev"]` (compose / k8s).
3. k8s `args: [..., "server", ..., "-dev", ...]`.
4. `VAULT_DEV_ROOT_TOKEN_ID=...` env var.
5. `VAULT_DEV_LISTEN_ADDRESS=...` env var.

Each occurrence emits one finding line.

## CWE / standards

- **CWE-798**: Use of Hard-coded Credentials.
- **CWE-1188**: Insecure Default Initialization of Resource.
- **CWE-256 / CWE-257**: Plaintext / Recoverable storage of credentials.
- HashiCorp Vault docs: "Dev mode is insecure and loses data on
  every restart. Do not run dev mode in production."

## What we accept (no false positive)

- `vault server -config=/etc/vault/vault.hcl` (production form).
- HCL config files with `storage`, `listener`, `seal` blocks.
- README / comments that mention `vault server -dev` only as a
  warning ("Do NOT run: vault server -dev").
- k8s `args: ["server", "-config=..."]`.

## What we flag

- Dockerfile `CMD ["vault","server","-dev",...]`.
- Shell wrapper `exec vault server -dev ...`.
- docker-compose `command: [...,"-dev",...]`.
- docker-compose `environment: { VAULT_DEV_ROOT_TOKEN_ID: ... }`.
- k8s Deployment `args: ["server","-dev"]`.
- systemd `ExecStart=/usr/local/bin/vault server --dev`.

## Limits / known false negatives

- We do not flag manual `export VAULT_TOKEN=root` in a shell script
  (that is a different anti-pattern, separate detector).
- We do not flag a real config file that itself sets
  `disable_mlock = true` or `tls_disable = 1` (separate detectors
  in this series).

## Usage

```bash
python3 detect.py path/to/Dockerfile
python3 detect.py path/to/repo/
```

Exit codes: `0` = no findings, `1` = findings (printed to stdout),
`2` = usage error.

## Smoke test

```
$ bash smoke.sh
bad=6/6 good=0/6
PASS
```

Layout:

```
examples/bad/
  01_dockerfile_exec.Dockerfile      # CMD ["vault","server","-dev",...]
  02_shell_wrapper.sh                # exec vault server -dev ...
  03_compose_env.yaml                # VAULT_DEV_ROOT_TOKEN_ID env
  04_k8s_args.yaml                   # args: ["server","-dev"]
  05_systemd_unit.service            # ExecStart=... vault server --dev
  06_compose_command_array.yaml      # command: [...,"-dev",...]
examples/good/
  01_dockerfile_config.Dockerfile    # CMD with -config=...
  02_vault_config.hcl                # real HCL config (raft + tls)
  03_prod_launcher.sh                # exec vault server -config=...
  04_k8s_statefulset.yaml            # args: ["server","-config=..."]
  05_doc_only_in_comments.hcl        # mentions -dev only in comments
  06_compose_config.yaml             # command: [...,"-config=..."]
```
