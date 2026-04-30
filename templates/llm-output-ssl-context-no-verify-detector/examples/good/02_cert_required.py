"""good: explicit CERT_REQUIRED — the safe value."""
import ssl

ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
ctx.verify_mode = ssl.CERT_REQUIRED
ctx.check_hostname = True
ctx.load_default_certs()
