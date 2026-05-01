# llm-output-kubernetes-secret-base64-plaintext-detector

Single-pass python3 stdlib scanner for Kubernetes `Secret`
manifests committed with plaintext-equivalent credentials. Flags
`data:` values whose base64 decodes to known credential prefixes
(`AKIA…`, `sk_live_…`, `ghp_…`, `glpat-…`, `AIza…`, PEM private
keys, JWTs) or to high-entropy passwords; flags `stringData:`
values directly; and flags malformed `data:` values where the
author skipped the base64 step entirely.

## Why it exists

A `kind: Secret` stores values base64-*encoded*, not encrypted.
Anyone with read on the YAML — every reviewer on every PR, every
CI log line, every `git log -p` — recovers the secret with one
`base64 -d`. Yet LLMs cheerfully emit "production-ready" Secret
manifests with real-looking credentials encoded in `data:`,
because the schema demands base64 and the model has no concept
of "do not commit this".

Worse, the failure mode is silent: the manifest applies cleanly,
the pod boots, the secret works — and now the credential lives
forever in the repo's git history.

## What it flags

* `k8s-secret-data-with-base64-secret` — a `kind: Secret`
  manifest whose `data:` map decodes to a value that:
  - matches a known credential prefix (`AKIA…`, `ASIA…`,
    `sk_live_`, `sk_test_` *unless* clearly placeholder,
    `xoxb-` / `xoxp-` / `xoxa-` / `xoxr-` (Slack), `ghp_` /
    `gho_` / `ghs_` / `ghu_` / `github_pat_`, `glpat-`,
    `AIza…`, `ya29.`, `SG.`, `Bearer …`), OR
  - matches a PEM private-key header, OR
  - matches a JWT (`eyJ…\.…\.…`), OR
  - looks like a high-entropy password: >= 16 chars, >= 3
    character classes, >= 35% unique-char ratio.
* `k8s-secret-stringdata-with-secret` — same checks but applied
  to `stringData:` values directly (no decode needed).
* `k8s-secret-data-undecodable-non-placeholder` — `data:` value
  is not valid base64 AND is not a placeholder; almost certainly
  someone forgot the `base64` step and pasted the plaintext raw,
  which `kubectl apply` will reject with a confusing error and
  often gets "fixed" by base64-encoding the plaintext in place.

## What it does NOT flag

* Values that decode to obvious placeholders (`changeme`,
  `replace…`, `<…>`, `${…}`, `xxxx…`, `your-…`, single-class
  short words like `password` / `secret` / `admin`, all-same-char
  strings).
* Manifests that source secrets via `secretRef` /
  `valueFrom.secretKeyRef` / `envFrom.secretRef` (no value is
  embedded).
* CRDs that exist precisely to avoid committing plaintext:
  `SealedSecret`, `ExternalSecret`, `SecretStore`, `VaultAuth`,
  etc. (they don't match `kind: Secret`).
* Lines marked with a trailing `# k8s-secret-ok` comment.
* Empty `data:` / `stringData:` values.

## Usage

```bash
python3 detect.py path/to/file_or_dir [more paths ...]
```

Exit code:

- `0` — no findings
- `1` — at least one finding
- `2` — usage error

Multi-document YAML (`---`-separated) is supported; each
document is classified independently.

## Worked example

`examples/bad/` has 3 dangerous manifests producing 6 findings;
`examples/good/` has 2 safe manifests producing 0 findings.

```
$ ./verify.sh
bad findings:  6 (rc=1)
good findings: 0 (rc=0)
PASS
```

Verbatim scanner output on `examples/bad/`:

```
examples/bad/aws-stripe-secret.yaml:8:1:  k8s-secret-data-with-base64-secret  — data.AWS_ACCESS_KEY_ID: decodes to real-looking secret (prefix:'AKIA')
examples/bad/aws-stripe-secret.yaml:9:1:  k8s-secret-data-with-base64-secret  — data.AWS_SECRET_ACCESS_KEY: decodes to real-looking secret (high-entropy)
examples/bad/aws-stripe-secret.yaml:17:1: k8s-secret-data-with-base64-secret  — data.STRIPE_SECRET: decodes to real-looking secret (prefix:'sk_live_')
examples/bad/db-undecodable.yaml:8:1:     k8s-secret-data-undecodable-non-placeholder — data.POSTGRES_PASSWORD: not valid base64
examples/bad/github-stringdata.yaml:7:1:  k8s-secret-stringdata-with-secret    — stringData.GITHUB_TOKEN: real-looking secret (prefix:'ghp_')
examples/bad/github-stringdata.yaml:8:1:  k8s-secret-stringdata-with-secret    — stringData.webhook_password: real-looking secret (high-entropy)
# 6 finding(s)
```

## Suppression

Add `# k8s-secret-ok` at the end of any line you have audited —
e.g. a known-fake fixture used by a kind-cluster integration
test.

## Layout

```
llm-output-kubernetes-secret-base64-plaintext-detector/
├── README.md
├── detect.py
├── verify.sh
└── examples/
    ├── bad/
    │   ├── aws-stripe-secret.yaml
    │   ├── db-undecodable.yaml
    │   └── github-stringdata.yaml
    └── good/
        ├── external-secret.yaml
        └── placeholders.yaml
```

## Limitations

- Pure regex / line-oriented YAML parsing. Block scalars
  (`|`, `>`) and complex flow-style maps inside `data:` are not
  fully understood; values are read line-by-line.
- The high-entropy heuristic will miss short but real passwords
  (< 16 chars). It also won't flag a base64 value whose decoded
  bytes are binary garbage but happen to be a real cryptographic
  secret blob — those are accepted as "decodes cleanly, looks
  not-placeholder" only via the known-prefix path.
- A `Secret` whose values are merged in via Kustomize
  `secretGenerator` is invisible until `kustomize build` is run;
  point the scanner at the rendered manifest in CI.
- Custom credential prefixes (vendor-specific) are not
  enumerated exhaustively; extend `KNOWN_PREFIXES` for your
  estate.
