from cryptography.hazmat.primitives.hmac import HMAC
from cryptography.hazmat.primitives import hashes
h = HMAC(b"baked-in-hmac-secret-bytes", hashes.SHA256())
