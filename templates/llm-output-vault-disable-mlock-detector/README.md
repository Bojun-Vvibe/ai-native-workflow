# llm-output-vault-disable-mlock-detector

Detects HashiCorp Vault server configurations that set
`disable_mlock = true` outside the narrow contexts where it is
documented as safe (integrated storage on systems where mlock is
impossible, e.g. some container runtimes that drop `IPC_LOCK`).

Surfaces covered:

* `vault.hcl` / `config.hcl` (HCL)
* Helm `values.yaml` for the official Vault chart (`server.extraConfig`
  or `server.ha.config` block embedding HCL, plus the chart's own
  `server.disableMlock` toggle)
* `docker-compose.yml` env (`VAULT_DISABLE_MLOCK=true`)
* Dockerfile / shell `ENV VAULT_DISABLE_MLOCK true`

## Why this matters

Vault stores unsealed keys, tokens, and decrypted secrets in process
memory. `mlock(2)` keeps those pages off swap and out of core dumps.
Disabling it means a host-level memory pressure event, a swap-backed
hibernate, or a `gcore`-style operator action can spill plaintext
secrets to disk where they outlive the Vault process and bypass every
audit-device guarantee.

The official Vault production hardening guide
(`learn.hashicorp.com/tutorials/vault/production-hardening`) calls
mlock out as a required mitigation. The HCL reference explicitly
warns that `disable_mlock` "should be avoided in production".

LLM-generated quickstarts disable it by reflex because the dev-mode
container logs a warning when mlock is unavailable, and the easiest
way to silence the warning is to flip the toggle. That silences the
warning and the protection at the same time.

## Rules

A finding is emitted when a recognised Vault config surface sets
the disable toggle to a truthy literal:

* HCL: `disable_mlock = true` (also `"true"`, `1`, `yes`, `on`)
* Compose / Dockerfile / shell env: `VAULT_DISABLE_MLOCK=true`
  (and the same truthy variants)
* Helm values: `server.disableMlock: true` at any nesting level,
  or an embedded HCL block containing the HCL form

Suppression: the magic comment `# vault-disable-mlock-allowed`
anywhere in the file silences the finding. Use only when the
deployment target genuinely cannot grant `IPC_LOCK` (some serverless
runtimes) and the operator has a separate swap-disabled / no-coredump
posture.

## Run

```
python3 detector.py examples/bad/01_vault_hcl_default.hcl
./verify.sh
```

`verify.sh` exits 0 when the detector flags 4/4 bad and 0/4 good.

## Out of scope

* Vault listener TLS posture (`tls_disable = true`) — separate
  detector niche.
* Seal stanza misconfiguration (auto-unseal key exposure) — separate
  detector niche.
* Strength of the unseal-key sharing scheme — operational, not a
  config-shape problem.

## References

* HashiCorp Vault docs, `disable_mlock` parameter — flagged as
  production-discouraged.
* HashiCorp Vault production hardening guide — mlock listed as a
  required control.
