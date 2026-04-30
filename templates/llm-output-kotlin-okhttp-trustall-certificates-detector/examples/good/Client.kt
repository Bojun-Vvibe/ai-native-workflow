package example

import okhttp3.OkHttpClient
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManagerFactory
import java.security.KeyStore

// Good: rely on the platform default trust store and the platform's
// default hostname verifier. No trust-all manager is constructed, no
// permissive HostnameVerifier lambda is used.
fun buildClient(keystore: KeyStore): OkHttpClient {
    val tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm()
    )
    tmf.init(keystore)
    val ctx = SSLContext.getInstance("TLS")
    ctx.init(null, tmf.trustManagers, null)

    // Note: we deliberately do NOT call .hostnameVerifier(...) so the
    // OkHttp default verifier (which honours SAN / CN) is used.
    return OkHttpClient.Builder()
        .sslSocketFactory(ctx.socketFactory, tmf.trustManagers[0] as javax.net.ssl.X509TrustManager)
        .build()
}

// Strings that mention "checkServerTrusted" or
// "hostnameVerifier { _, _ -> true }" inside literals must NOT trip
// the detector — they are masked.
val docstring = "Do not write checkServerTrusted(...) {} bodies."
val warning = "Avoid .hostnameVerifier { _, _ -> true } in production."
