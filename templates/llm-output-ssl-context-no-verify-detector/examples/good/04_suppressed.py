"""good: localhost-only test fixture explicitly opts out via # ssl-ok."""
import ssl

ctx = ssl._create_unverified_context()  # ssl-ok: pinned to 127.0.0.1 unit test
ctx.check_hostname = False  # ssl-ok: localhost loopback only
ctx.verify_mode = ssl.CERT_NONE  # ssl-ok: localhost loopback only
print(ctx)
