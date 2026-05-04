# llm-output-temporal-frontend-tls-disabled-detector

Static lint that flags Temporal server YAML configs which disable
TLS, mTLS, or certificate hostname verification on the frontend or
internode listeners.

## Why this matters

Temporal's `global.tls` block governs the wire format for the
frontend (gRPC SDK clients), the internode mesh (frontend ↔
matching ↔ history ↔ worker), and Web UI access. Three regressions
that LLM-generated configs commonly introduce all collapse the
security model:

1. **`global.tls.frontend` missing or `null`** while the listener
   binds a non-loopback address. Plain gRPC over the wire — anyone
   with network reach can call `StartWorkflowExecution`,
   `DescribeNamespace`, `TerminateWorkflowExecution`, etc.
2. **`disableHostVerification: true`** on the client side. The
   handshake completes, but Temporal will accept *any* cert from
   *any* peer presenting a valid cert chain; trivial MITM in any
   environment where attacker can intercept the gRPC stream.
3. **`requireClientAuth: false`** on the frontend server. Server
   presents a cert; clients are not asked for one. Anyone who can
   route to the listener can call frontend RPCs.

The "hello-world" Temporal config that ships in tutorial blog posts
omits `global.tls` entirely because dev mode runs on `127.0.0.1`.
Learners paste it into prod with one line changed (`bindOnIP:
0.0.0.0`) and ship plaintext gRPC.

## What it catches

- `services.frontend.rpc.bindOnIP` is non-loopback (or unset →
  defaults to all interfaces) and `global.tls` is absent.
- `global.tls.frontend` is `null`, `{}`, or has no `certFile` while
  the frontend listener is non-loopback.
- Any `disableHostVerification: true` under `global.tls.*.client`.
- `global.tls.frontend.server.requireClientAuth: false`.

## What it does NOT catch (yet)

- Cert / key file path traversal sanity (e.g. files unreadable by
  the temporal user).
- Cipher-suite downgrades (`global.tls.frontend.server.tlsMinVersion`).
- Web UI (`temporal-ui`) auth bypass — that is a different config
  surface; see the corresponding `temporal-ui` detector when added.

## Suppression

Add a top-of-file comment to suppress in test fixtures:

```yaml
# temporal-tls-disabled-allowed
```

## Usage

```
python3 detector.py path/to/temporal/config.yaml
```

Exit code is the number of files with at least one finding (capped
at 255).

## Worked example

```
$ ./verify.sh
bad=4/4 good=0/3
PASS
```

## CWE refs

- CWE-295: Improper Certificate Validation
- CWE-319: Cleartext Transmission of Sensitive Information
- CWE-306: Missing Authentication for Critical Function
