# llm-output-go-tls-insecureskipverify-detector

Pure-stdlib python3 line scanner that flags `InsecureSkipVerify: true`
and `InsecureSkipVerify = true` in LLM-emitted Go source. The field
disables peer certificate validation in `crypto/tls`, and an enabled
client is wide open to any on-path attacker performing TLS MITM.

## Why

Both struct-literal and field-assignment forms appear in the wild,
across `net/http` clients, `database/sql` drivers, gRPC dial options
via `credentials.NewTLS`, AMQP, Kafka, MongoDB, and "I just want to
talk to my self-signed cert" snippets. The Go standard library's
`crypto/tls` documentation states the field "should be used only for
testing or in combination with VerifyConnection or
VerifyPeerCertificate". LLMs almost never emit either callback when
they emit `InsecureSkipVerify: true`, so the resulting code skips
all chain validation, hostname matching, and revocation checks.

CWE references:

- **CWE-295**: Improper Certificate Validation.
- **CWE-297**: Improper Validation of Certificate with Host Mismatch.

## Usage

```sh
python3 detect.py path/to/foo.go
python3 detect.py path/to/cmd/   # recurses *.go (skips *_test.go)
```

Exit code 1 if any unsafe usage found, 0 otherwise.

## What it flags

A line in a `.go` file containing any of:

- `InsecureSkipVerify: true` (struct-literal field, any whitespace)
- `InsecureSkipVerify = true` (field assignment on an existing value)
- `InsecureSkipVerify : true` (rare YAML-style spacing)

The boolean must be the literal `true`. A variable like
`InsecureSkipVerify: skipVerify` is not flagged, because the value is
data-flow-dependent and the call site might still be safe.

## What it does NOT flag

- `InsecureSkipVerify: false` — explicit-safe.
- The field name appearing inside a string literal (interpreted,
  rune, or raw backtick-delimited) or after a `//` line comment.
  Handled by a Go-aware line stripper.
- Lines suffixed with `// insecureskipverify-ok`.
- Test files (`*_test.go`). TLS short-circuiting in tests is common
  practice and lower-risk; pass an explicit path to scan one anyway.

## Worked example

```sh
cd templates/llm-output-go-tls-insecureskipverify-detector
./verify.sh
```

`verify.sh` runs the detector against `examples/bad/` (multiple
positive cases — http client, gRPC `credentials.NewTLS`, field
assignment, Kafka-style nested config, raw whitespace variant) and
`examples/good/` (explicit `false`, suppressed line, value driven by
a variable, string-literal mention only). It asserts:

- detector exits non-zero on `bad/` with at least the expected number
  of findings,
- detector exits zero on `good/` with zero findings,
- prints `PASS` if both hold.
