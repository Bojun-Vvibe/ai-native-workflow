"""bad: bare CERT_NONE assignment imported via from-import."""
import ssl
from ssl import CERT_NONE

context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
context.verify_mode = CERT_NONE
context.check_hostname = False
