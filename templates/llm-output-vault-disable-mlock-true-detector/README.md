# llm-output-vault-disable-mlock-true-detector

Detects LLM-emitted HashiCorp Vault server configurations that set
`disable_mlock = true` in production-style deployments. Vault uses `mlock(2)`
to keep sensitive in-memory material (encryption keys, unsealed secrets) from
being written to swap. Disabling it allows secret bytes to leak to disk via
the swap file, where they may persist after the process exits or the host
reboots.

`disable_mlock` is only legitimate in two narrow cases: integrated storage
on hosts where swap is provably absent, or in-memory `dev` mode. LLMs often
copy `disable_mlock = true` from quickstart blog posts straight into HCL,
docker-compose, k8s ConfigMaps, and Helm values, leaving production servers
swapping seal keys to disk.

## What this catches

| # | Pattern                                                                                              |
|---|------------------------------------------------------------------------------------------------------|
| 1 | HCL: `disable_mlock = true` (any spacing, any quoting) at top level of a Vault config                |
| 2 | Env var form: `VAULT_DISABLE_MLOCK=1` / `=true` / `="true"` in systemd, Dockerfile, .env-style files |
| 3 | docker-compose / k8s manifest passing `--config` HCL inline or env that sets the disable             |
| 4 | Helm values: `server.extraArgs` / `server.config` containing `disable_mlock = true`                  |

CWE-922 (Insecure Storage of Sensitive Information) — sealed/unsealed key
material can be paged to swap.

## Usage

```bash
./detector.sh examples/bad/* examples/good/*
```

Exit 0 iff every bad sample fires and zero good samples fire. The trailing
status line is `bad=N/N good=0/M PASS|FAIL`.

## Worked example

Run `./run-test.sh` from this directory. It runs the detector against the
bundled samples and asserts `bad=4/4 good=0/3 PASS`.
