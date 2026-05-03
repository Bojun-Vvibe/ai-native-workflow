# llm-output-vault-listener-tls-disable-detector

Static lint that flags HashiCorp Vault server HCL configurations
whose `listener "tcp"` block sets `tls_disable = true` on a
non-loopback bind address.

Vault's HTTP API ships unseal keys, root tokens, secret reads, and
policy writes for the entire cluster. Disabling TLS on the listener
moves all of that traffic — including the Vault token in the
`X-Vault-Token` header on every request — to plaintext on the
network (CWE-319). Combined with a non-loopback `address` (anything
other than `127.0.0.1`, `[::1]`, or `localhost`), any device on the
broadcast domain can capture credentials and impersonate clients.

LLM-generated `vault.hcl` / `server.hcl` files routinely emit:

```hcl
listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true
}
```

or:

```hcl
listener "tcp" {
  address     = "10.0.1.5:8200"
  tls_disable = "true"
}
```

This detector parses each top-level `listener "tcp" { ... }` HCL
block and flags blocks where `tls_disable` is truthy AND the
`address` is not a loopback address.

## What it catches

- `listener "tcp"` blocks with `tls_disable = true` (or `"true"`,
  `1`, `"1"`, `yes`).
- Missing `address` (Vault defaults to `0.0.0.0:8200` — non-loopback).
- IPv6 non-loopback binds and bracketed IPv6 host parsing.

## CWE references

- [CWE-319](https://cwe.mitre.org/data/definitions/319.html):
  Cleartext Transmission of Sensitive Information
- [CWE-311](https://cwe.mitre.org/data/definitions/311.html):
  Missing Encryption of Sensitive Data
- [CWE-522](https://cwe.mitre.org/data/definitions/522.html):
  Insufficiently Protected Credentials

## False-positive surface

- Files containing `# vault-tls-disable-allowed` are skipped wholesale
  (use for committed dev fixtures).
- Loopback bind (`address = "127.0.0.1:8200"`, `localhost:*`,
  `[::1]:*`) is accepted even with `tls_disable = true`.
- `listener "unix"` blocks are not flagged (no TLS option exists).
- `tls_disable = false` (the default) is not flagged.

## Worked example

```sh
$ ./verify.sh
bad=4/4 good=0/3
PASS
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `run.sh` — thin wrapper that execs `verify.sh`.
- `smoke.sh` — alias for `run.sh`, kept for harness symmetry.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
