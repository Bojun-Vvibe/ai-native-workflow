# llm-output-grpc-server-no-tls-detector

Single-pass python3 stdlib scanner for gRPC server (and adjacent
client) constructions that omit TLS / use insecure credentials.
Flags the canonical "plaintext gRPC in production" shapes LLMs
emit across Go (`google.golang.org/grpc`), Python
(`grpcio`), Java (`io.grpc`), and Node (`@grpc/grpc-js`).

## Why it exists

gRPC servers default to plaintext if no transport credentials are
supplied. Unlike HTTP/1.1 behind a TLS-terminating ingress, gRPC
is typically called pod-to-pod or service-to-service and frequently
bypasses any ingress TLS termination — so "the proxy handles TLS"
is rarely true for internal services.

A gRPC server without TLS exposes every RPC payload — auth tokens,
PII, internal call metadata — to any on-path observer. LLM-emitted
snippets routinely fall into this trap because:

- `grpc.NewServer()` with no options compiles, runs, and looks
  reasonable in a quickstart.
- Python `add_insecure_port` is one character shorter than
  `add_secure_port` and shows up first in many tutorials.
- Java `ServerBuilder.forPort(p).build().start()` is the most
  copy-pasteable gRPC snippet in existence and skips the whole
  `useTransportSecurity` chain.
- Node `grpc.ServerCredentials.createInsecure()` is what the
  official quickstart still uses.

## What it flags

Go (`*.go`):

- `grpc.NewServer(...)` whose argument list contains no
  `grpc.Creds(` token → `grpc-go-server-no-creds`.
- `insecure.NewCredentials()` → `grpc-go-insecure-credentials`.
- `grpc.WithInsecure()` → `grpc-go-with-insecure`.

Python (`*.py`):

- `add_insecure_port(` on a server object →
  `grpc-py-add-insecure-port`.
- `grpc.insecure_channel(` in a non-test path →
  `grpc-py-insecure-channel`.

Java (`*.java`):

- `ServerBuilder.forPort(...)` not followed within 6 lines by
  `.useTransportSecurity(` or `.sslContext(` →
  `grpc-java-server-no-tls`.

Node (`*.js`, `*.ts`, `*.mjs`, `*.cjs`):

- `grpc.ServerCredentials.createInsecure(` →
  `grpc-js-server-credentials-insecure`.

## What it does NOT flag

- `grpc.NewServer(grpc.Creds(creds))` in Go.
- `server.add_secure_port(...)` in Python.
- `ServerBuilder.forPort(p).useTransportSecurity(certFile, keyFile)`
  in Java within the 6-line window.
- `grpc.ServerCredentials.createSsl(...)` in Node.
- Lines marked with a trailing `# grpc-no-tls-ok` or
  `// grpc-no-tls-ok` comment.
- Patterns inside `#` or `//` comment lines.
- Files under any path segment named `test`, `tests`, `_test`,
  `__tests__`, `testdata`, or with a name ending in `_test.go`,
  `.test.js`, `.test.ts`, `.test.mjs`, `.test.cjs`.

## Usage

```
python3 detect.py <file_or_dir> [...]
```

Exit code `1` on findings, `0` otherwise. python3 stdlib only.

Run the bundled worked example:

```
./verify.sh
```

## Verified output

```
=== bad ===
examples/bad/server.py:8: grpc-py-add-insecure-port: server.add_insecure_port("[::]:50051")
examples/bad/server.py:14: grpc-py-insecure-channel: channel = grpc.insecure_channel("payments.internal:50051")
examples/bad/HelloServer.java:8: grpc-java-server-no-tls: Server server = ServerBuilder.forPort(50051)
examples/bad/server.js:7: grpc-js-server-credentials-insecure: grpc.ServerCredentials.createInsecure(),
examples/bad/client_insecure.go:9: grpc-go-insecure-credentials: creds := insecure.NewCredentials()
examples/bad/client_insecure.go:14: grpc-go-with-insecure: return grpc.Dial(addr, grpc.WithInsecure())
examples/bad/server_no_creds.go:16: grpc-go-server-no-creds: s := grpc.NewServer()
=== good ===
=== verify ===
bad findings:  7 (rc=1)
good findings: 0 (rc=0)
PASS
```
