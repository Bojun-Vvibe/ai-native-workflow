# llm-output-vault-root-token-hardcoded-detector

Detects HashiCorp Vault deployments that ship a hardcoded **root token**
in plain configuration — `.env`, Docker-Compose, Kubernetes manifests,
HCL config, or shell-export bootstrap scripts.

## Why this matters

`vault operator init` returns a single root token whose entire purpose
is to bootstrap a real auth backend (userpass, OIDC, AppRole, K8s auth,
…). Once that backend exists, the canonical step is:

```
vault token revoke <root-token>
```

A root token that survives in a config file means:

* Anyone who can read the file (CI logs, repo history, image layer,
  shared chat) gains unrestricted read/write on every secret in every
  namespace.
* Audit logs cannot attribute actions — every call from that file looks
  like the same root principal.
* The token cannot be scoped, TTL-limited, or revoked granularly without
  invalidating everything that reads from the same file.

The dev-mode placeholders (`root`, `myroot`, `devroot`, …) are even
worse: tutorial code routinely targets them, so leaving one in
production turns every "hello world" Vault snippet on the internet into
a working credential.

## What this detector matches

For each scanned file, the detector flags any assignment to
`VAULT_TOKEN`, `VAULT_DEV_ROOT_TOKEN_ID`, or HCL `token = "…"` (when the
surrounding context mentions a Vault config block) where the right-hand
side is a **token-shaped literal**:

* Starts with `hvs.`, `hvb.`, `s.`, or `b.` (real Vault token prefixes).
* Equals one of the well-known dev placeholders
  (`root`, `myroot`, `vault-root`, `rootroot`, `devroot`, `mytoken`,
  `changeme`).
* Is a 16+ character alphanumeric/dash literal with no shell or
  templating interpolation.

It also handles the Kubernetes env-list pattern: a `name: VAULT_TOKEN`
entry whose sibling is `value: <literal>` (rather than `valueFrom:`).

### Ignored (good)

* Empty values.
* References: `${VAULT_TOKEN}`, `$VAULT_TOKEN`, `${VAULT_TOKEN:-}`,
  `%(env:VAULT_TOKEN)s`, `<REPLACE_ME>`, `{{ .Values.token }}`.
* Kubernetes env entries that use `valueFrom: secretKeyRef:` (no inline
  `value:` field).
* Lines carrying the inline marker `# vault-root-token-allowed`.

The detector is regex-based and intentionally conservative — it does
not try to parse arbitrary HCL or YAML, and it requires a
clearly-token-shaped value rather than guessing about every secret-like
string.

## Usage

```
python3 detector.py path/to/file_or_dir [more paths ...]
```

Exit code is the number of files with at least one finding (capped at
255). Stdout lines have the form `<file>:<line>:<reason>`.

## Worked example

Run `./verify.sh` against the bundled corpus:

```
$ ./verify.sh
bad=4/4 good=0/4
PASS
```

Per-file detector output:

```
--- examples/bad/01_dotenv_hvs_token.envfile ---
examples/bad/01_dotenv_hvs_token.envfile:4:VAULT_TOKEN: hardcoded Vault token literal (prefix 'hvs.') baked into config
exit=1
--- examples/bad/02_compose_dev_root.yaml ---
examples/bad/02_compose_dev_root.yaml:8:VAULT_DEV_ROOT_TOKEN_ID: placeholder root-token literal 'myroot' baked into config
examples/bad/02_compose_dev_root.yaml:14:VAULT_TOKEN: placeholder root-token literal 'myroot' baked into config
exit=1
--- examples/bad/03_k8s_deployment_inline_value.yaml ---
examples/bad/03_k8s_deployment_inline_value.yaml:22:k8s env VAULT_TOKEN: hardcoded Vault token literal (prefix 'hvs.') baked into config
exit=1
--- examples/bad/04_shell_export_legacy_prefix.sh ---
examples/bad/04_shell_export_legacy_prefix.sh:8:VAULT_TOKEN: hardcoded Vault token literal (prefix 's.') baked into config
exit=1
--- examples/good/01_dotenv_interpolated.envfile ---
exit=0
--- examples/good/02_compose_env_reference.yaml ---
exit=0
--- examples/good/03_k8s_deployment_secretref.yaml ---
exit=0
--- examples/good/04_local_dev_suppressed.sh ---
exit=0
```

## Remediation

* Revoke the leaked root token immediately:
  `vault token revoke <token>`.
* Rotate any secret the token could read (assume compromise).
* Replace the literal with a runtime reference — `${VAULT_TOKEN}` from
  the host environment, K8s `secretKeyRef`, AppRole auth + short-lived
  child token, or the agent template sidecar.
* Add the suppression marker `# vault-root-token-allowed` only on
  fixtures/test scripts that intentionally use the dev-mode `root`
  placeholder against a local Vault.
