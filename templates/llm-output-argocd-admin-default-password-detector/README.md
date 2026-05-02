# llm-output-argocd-admin-default-password-detector

Detect Argo CD install / config snippets that leave the bootstrap `admin`
account exposed — either by keeping a known weak literal password, by
shipping a config that enables the local admin without rotating the
generated bootstrap password, or by handing out the default password on
`argocd login` command lines that end up in scripts.

LLMs frequently emit "easy bootstrap" Argo CD instructions that paste the
default `admin` / `admin` credentials into Secrets, Helm values, or
`argocd login` invocations. Once that material lands in a repo or shell
history, anyone who can reach the API server can take over every Application
on the cluster.

## What bad LLM output looks like

A `Secret` shipping a known weak literal in `stringData`:

```yaml
stringData:
  admin.password: admin
```

A `Secret` shipping a base64-encoded weak literal in `data`:

```yaml
data:
  admin.password: YWRtaW4=   # base64("admin")
```

An `argocd-cm` that re-enables the local admin but never rotates the
bootstrap password (no `admin.passwordMtime` / `admin.passwordHash`
companion):

```yaml
data:
  admin.enabled: "true"
```

A login script with the default password baked in:

```sh
argocd login localhost:8080 --username admin --password admin
```

Helm values that pin a weak admin password:

```yaml
configs:
  secret:
    argocdServerAdminPassword: admin123
```

## What good LLM output looks like

Local admin disabled, SSO enforced:

```yaml
data:
  admin.enabled: "false"
  oidc.config: |
    ...
```

Or local admin enabled but with a rotated bcrypt hash and matching mtime:

```yaml
stringData:
  admin.passwordHash: "$2a$10$..."
  admin.passwordMtime: "2025-08-14T09:32:11Z"
```

Or login scripts that pull the rotated password from a secret manager:

```sh
ARGO_PW="$(vault kv get -field=password secret/argocd/admin)"
argocd login argocd.example.com --username admin --password "$ARGO_PW"
```

## Run the smoke test

```sh
bash detect.sh samples/bad/* samples/good/*
```

Expected output:

```
BAD  samples/bad/argocd_cm_admin_enabled_no_rotate.yaml
BAD  samples/bad/argocd_secret_b64_admin.yaml
BAD  samples/bad/argocd_secret_literal_admin.yaml
BAD  samples/bad/helm_values_weak.yaml
BAD  samples/bad/login_default_admin.sh
GOOD samples/good/argocd_cm_sso_only.yaml
GOOD samples/good/argocd_secret_rotated.yaml
GOOD samples/good/login_from_vault.sh
bad=5/5 good=0/3 PASS
```

Exit status is `0` only when every bad sample is flagged and zero good samples
are flagged.

## Detector rules

1. `admin.password:` set to a known weak literal (`admin`, `password`,
   `argocd`, `admin123`, `changeme`) in either `stringData` or `data`
   (including the base64 forms `YWRtaW4=`, `cGFzc3dvcmQ=`, `YXJnb2Nk`,
   `YWRtaW4xMjM=`).
2. `argocd login --password <weak>` invocations using one of the same
   weak literals.
3. `admin.enabled: "true"` in `argocd-cm` with no companion
   `admin.passwordMtime` / `admin.passwordHash` rotation marker — i.e. the
   bootstrap password is still in effect.
4. Helm or kustomize values that pin `argocdServerAdminPassword` (or the
   snake-case variant) to a known weak literal.
