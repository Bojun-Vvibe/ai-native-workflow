"""good: default secure context, full verification."""
import ssl
from urllib.request import urlopen

ctx = ssl.create_default_context()
# verify_mode is CERT_REQUIRED and check_hostname is True by default.
print(urlopen("https://example.com/", context=ctx).status)
