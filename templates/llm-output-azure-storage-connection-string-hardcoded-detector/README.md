# llm-output-azure-storage-connection-string-hardcoded-detector

Single-pass python3 stdlib scanner for hardcoded Azure Storage
credentials in source / config / scripts. Flags full
`AccountKey=`-bearing connection strings, embedded
`SharedAccessSignature=` segments, bare `accountKey="…"`
assignments, dotenv-style `AZURE_STORAGE_KEY=…` lines, and SAS
query strings (`?sv=YYYY-MM-DD&…&sig=…`) pasted into URLs.

## Why it exists

Azure Storage account keys are *full-control* credentials: anyone
with the key can read, write, and delete every blob, queue,
table, and file share on the account, and can mint arbitrary SAS
tokens out of band. There is no per-container scoping, no
revocation other than rolling the key, and the key is paired
with a 40+ year crypto-shaped base64 string that LLMs can't tell
apart from a placeholder. The wire shape is unmistakable —
`DefaultEndpointsProtocol=…;AccountName=…;AccountKey=…` — and
LLMs reproduce it verbatim from "quick start" docs whenever they
generate Azure Storage glue code.

The same shape leaks into committed `.env`, into
`appsettings.json`, into Bicep / Terraform local-exec strings,
and into Markdown how-to snippets. SAS tokens with multi-year
`se=` (expiry) are routinely pasted as raw URLs because they
"just work" in `curl`.

## What it flags

* `azure-storage-connection-string-with-account-key` — a literal
  containing `DefaultEndpointsProtocol=` / `AccountName=` /
  `BlobEndpoint=` together with `AccountKey=<base64-ish>` (>= 20
  chars, not a placeholder).
* `azure-storage-connection-string-with-sas` — same shape but
  with `SharedAccessSignature=sv=YYYY-MM-DD&…&sig=…`.
* `azure-storage-bare-account-key-assignment` — variable / JSON
  key matching `(account|storage)[ _-]?key` (case-insensitive)
  assigned a quoted ~40+ char base64 string, OR a dotenv line
  `AZURE_STORAGE_KEY=` / `AZURE_STORAGE_ACCOUNT_KEY=` /
  `STORAGE_ACCOUNT_KEY=` with a base64-ish value.
* `azure-storage-sas-token-in-url` — any string containing
  `?sv=YYYY-MM-DD&…&sig=<base64-ish>` (a service or account
  SAS), where `<sig>` is at least 20 chars of urlencoded base64.

## What it does NOT flag

* Values that look like placeholders: `<your-key>`,
  `${AZURE_STORAGE_KEY}`, `{{key}}`, `%KEY%`, contain the words
  `your` / `placeholder` / `example` / `redacted` / `dummy` /
  `changeme`, contain `xxxxxx`+, or are a single character
  repeated 90%+ of the value.
* Use of `DefaultAzureCredential`, `ManagedIdentityCredential`,
  Key Vault references, or env-only access (`os.environ[...]`,
  `process.env...`) where no key literal appears in source.
* Lines marked with a trailing `# az-storage-key-ok` comment
  (or `// az-storage-key-ok`).
* Patterns inside `#`- or `//`-only comment lines.

## Usage

```bash
python3 detect.py path/to/file_or_dir [more paths ...]
```

Exit code:

- `0` — no findings
- `1` — at least one finding
- `2` — usage error

## Worked example

`examples/bad/` has 4 dangerous artefacts producing 5 findings;
`examples/good/` has 3 safe artefacts producing 0 findings.

```
$ ./verify.sh
bad findings:  5 (rc=1)
good findings: 0 (rc=0)
PASS
```

Verbatim scanner output on `examples/bad/` (snippets truncated
in this README for line width — the scanner emits full lines):

```
examples/bad/bad.dotenv:2:1: azure-storage-bare-account-key-assignment — AZURE_STORAGE_KEY=Zm9vYmFy…
examples/bad/config.json:4:5: azure-storage-bare-account-key-assignment — "accountKey": "QkFE…
examples/bad/sas.js:2:79: azure-storage-sas-token-in-url — const downloadUrl = "https://…
examples/bad/sas.js:3:18: azure-storage-connection-string-with-sas — const sasConn = "BlobEndpoint=…
examples/bad/upload.py:4:9: azure-storage-connection-string-with-account-key — CONN = "DefaultEndpointsProtocol=…
# 5 finding(s)
```

## Suppression

Add `# az-storage-key-ok` (or `// az-storage-key-ok`) at the end
of any line you have audited — for example, a fixture used only
by an offline unit test against the Azurite emulator.

## Layout

```
llm-output-azure-storage-connection-string-hardcoded-detector/
├── README.md
├── detect.py
├── verify.sh
└── examples/
    ├── bad/
    │   ├── bad.dotenv
    │   ├── config.json
    │   ├── sas.js
    │   └── upload.py
    └── good/
        ├── client.py
        ├── config.json
        └── dotenv.example
```

## Limitations

- Pure regex, no parsing — a connection string spread across
  multiple physical lines via string concatenation will be
  missed.
- Account keys shorter than 40 base64 chars (none in the wild
  for real Azure Storage, but possible in mocks) are skipped to
  avoid false positives on short tokens.
- SAS tokens that omit `sv=` (very old API versions) are not
  recognised.
- No crypto check on the captured base64 — anything matching the
  shape is reported. Use the `-ok` suppression on test fixtures.
