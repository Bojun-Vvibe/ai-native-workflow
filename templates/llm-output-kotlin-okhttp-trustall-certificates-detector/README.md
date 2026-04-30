# llm-output-kotlin-okhttp-trustall-certificates-detector

Static detector for Kotlin / OkHttp code that disables TLS certificate
or hostname verification — a textbook CWE-295 footgun an LLM happily
emits when asked to "fix" handshake errors.

```kotlin
// LLM "fix" — accepts any cert from any host.
val trustAllCerts = arrayOf<TrustManager>(object : X509TrustManager {
    override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {}
    override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {}
    override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
})
val sslContext = SSLContext.getInstance("TLS")
sslContext.init(null, trustAllCerts, SecureRandom())
val client = OkHttpClient.Builder()
    .sslSocketFactory(sslContext.socketFactory, trustAllCerts[0] as X509TrustManager)
    .hostnameVerifier { _, _ -> true }
    .build()
```

The correct shape is to use the platform default trust store
(`TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm())`),
or pin specific certificates with OkHttp's `CertificatePinner`, and to
**not** override the hostname verifier.

## What this flags

Three related shapes:

1. **trustall-trust-manager** — an `X509TrustManager` (or
   `X509ExtendedTrustManager`) whose `checkServerTrusted` /
   `checkClientTrusted` body is empty or just `return`, or whose
   `getAcceptedIssuers` returns `emptyArray()`, `arrayOf()`, or
   `null`. Also fires on `SSLContext.init(null, <anything>, ...)` —
   the canonical "wire up a trust-all manager" call.
2. **trustall-hostname-verifier** — `.hostnameVerifier { _, _ -> true }`,
   `.hostnameVerifier(HostnameVerifier { _, _ -> true })`, or an
   anonymous `object : HostnameVerifier` whose `verify` returns `true`.
3. **trustall-okhttp-builder** — an `OkHttpClient.Builder()` chain
   that calls `.sslSocketFactory(...)` in a file that also contains
   one of the above shapes — i.e. the place where the trust-all
   manager actually gets installed.

A finding is suppressed if the same logical line carries
`// llm-allow:trustall-tls`. Comments and string-literal interiors
are masked before pattern matching, so docstring examples don't fire.

The detector also extracts fenced `kt` / `kotlin` code blocks from
Markdown.

## CWE references

* **CWE-295**: Improper Certificate Validation.
* **CWE-297**: Improper Validation of Certificate with Host Mismatch.

## Usage

```
python3 detect.py <file_or_dir> [...]
```

Exit code `1` on any findings, `0` otherwise. python3 stdlib only.

## Worked example

```
$ bash verify.sh
bad findings:  6 (rc=1)
good findings: 0 (rc=0)
PASS
```

See `examples/bad/Client.kt` and `examples/good/Client.kt` for fixtures.
