package example

import okhttp3.OkHttpClient
import javax.net.ssl.HostnameVerifier
import javax.net.ssl.SSLContext
import javax.net.ssl.X509TrustManager
import java.security.cert.X509Certificate

// Bad #1: trust manager whose check methods are empty.
class TrustAllManager : X509TrustManager {
    override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {}
    override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {}
    override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
}

fun buildClient(): OkHttpClient {
    val trustAllCerts = arrayOf<javax.net.ssl.TrustManager>(TrustAllManager())
    val sslContext = SSLContext.getInstance("TLS")
    sslContext.init(null, trustAllCerts, java.security.SecureRandom())

    return OkHttpClient.Builder()
        .sslSocketFactory(sslContext.socketFactory, TrustAllManager())
        .hostnameVerifier { _, _ -> true }
        .build()
}

// Bad #2: anonymous HostnameVerifier object that always returns true.
val permissive = object : HostnameVerifier {
    override fun verify(hostname: String, session: javax.net.ssl.SSLSession): Boolean {
        return true
    }
}
