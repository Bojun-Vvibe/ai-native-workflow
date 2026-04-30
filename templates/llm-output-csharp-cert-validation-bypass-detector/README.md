# llm-output-csharp-cert-validation-bypass-detector

Pure-stdlib python3 line scanner that flags TLS certificate-validation
bypass patterns in LLM-emitted C# code.

## Why

When an LLM emits C# HTTPS client code and runs into a self-signed-cert
or hostname-mismatch error during "make it work" iteration, it
overwhelmingly reaches for one of three blunt instruments:

1. `ServicePointManager.ServerCertificateValidationCallback = (s, c, ch, e) => true;`
2. `HttpClientHandler { ServerCertificateCustomValidationCallback = HttpClientHandler.DangerousAcceptAnyServerCertificateValidator }`
3. `new HttpClientHandler { ServerCertificateCustomValidationCallback = (m, c, ch, e) => true }`
   (or the equivalent lambda body `return true;`).

Each of these disables the TLS chain check globally (form #1 — process-wide
side effect) or for every request through that handler (#2/#3). The
result: man-in-the-middle attackers with any certificate (including
expired, self-signed, or wrong-host) are silently trusted.

CWE references:

- **CWE-295**: Improper Certificate Validation.
- **CWE-297**: Improper Validation of Certificate with Host Mismatch.
- **CWE-345**: Insufficient Verification of Data Authenticity.

## Usage

```sh
python3 detect.py path/to/Foo.cs
python3 detect.py path/to/src/   # recurses *.cs
```

Exit code 1 if any unsafe usage found, 0 otherwise.

## What it flags

- Assignment to `ServicePointManager.ServerCertificateValidationCallback`
  with a lambda or delegate whose body is `=> true` or `return true;`.
- Assignment of `ServerCertificateCustomValidationCallback` to
  `HttpClientHandler.DangerousAcceptAnyServerCertificateValidator`.
- Assignment of `ServerCertificateCustomValidationCallback` to a lambda
  whose body is `=> true` or `return true;`.
- `RemoteCertificateValidationCallback` lambdas with the same shape
  (used with `SslStream`).

## What it does NOT flag

- Real callbacks that branch on `SslPolicyErrors` and return `false` for
  any error.
- Pinning logic that compares thumbprints / public-key hashes.
- Lines suffixed with `// cert-validation-ok` (audited test-only code).

## Verify the worked example

```sh
bash verify.sh
```

Asserts the detector flags every `examples/bad/*.cs` case and is
silent on every `examples/good/*.cs` case.
