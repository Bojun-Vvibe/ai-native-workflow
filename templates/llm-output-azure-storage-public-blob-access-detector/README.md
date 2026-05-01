# llm-output-azure-storage-public-blob-access-detector

Static lint that flags Terraform configurations making Azure storage
blobs publicly readable without authentication.

Azure Storage exposes two distinct public-access knobs that LLMs
routinely mis-set:

1. **Account-level ceiling**:
   `azurerm_storage_account.allow_nested_items_to_be_public` (formerly
   `allow_blob_public_access`). When `true`, any container in the
   account *may* opt into anonymous access. When `false`, no container
   can be public regardless of its own setting — a defense-in-depth
   ceiling.
2. **Container-level toggle**:
   `azurerm_storage_container.container_access_type`. Default is
   `"private"`. `"blob"` allows anonymous reads of individual blobs.
   `"container"` allows anonymous list + read of every blob.
3. **Network bypass**:
   `azurerm_storage_account_network_rules.default_action = "Allow"`
   opens the data plane to every IP on the public Internet — the
   opposite of the `"Deny"` allowlist posture you want.

LLM-generated Terraform routinely emits any of these without flagging
the implications. This detector catches them in `.tf`, `.tf.json`, and
`.tfvars` files.

## What it catches

- `allow_nested_items_to_be_public = true`
- `allow_blob_public_access = true` (legacy attribute name)
- `container_access_type = "blob"` or `"container"`
- `default_action = "Allow"` on `azurerm_storage_account_network_rules`
- `public_network_access_enabled = true` on the account

## CWE references

- [CWE-732](https://cwe.mitre.org/data/definitions/732.html): Incorrect
  Permission Assignment for Critical Resource
- [CWE-200](https://cwe.mitre.org/data/definitions/200.html): Exposure
  of Sensitive Information to an Unauthorized Actor
- [CWE-284](https://cwe.mitre.org/data/definitions/284.html): Improper
  Access Control

## False-positive surface

- Public static-site hosting containers (`$web`, `public-assets`) that
  *are* meant to be world-readable. Suppress per line with a trailing
  `# storage-public-allowed` comment.

## Worked example

```sh
$ ./verify.sh
bad=5/5 good=0/3
PASS
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
