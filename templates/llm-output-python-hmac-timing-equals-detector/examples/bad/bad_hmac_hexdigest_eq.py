"""Bad: comparing an HMAC hexdigest with `==` is timing-unsafe."""
import hmac
import hashlib


def verify(msg: bytes, key: bytes, provided_sig: str) -> bool:
    expected_sig = hmac.new(key, msg, hashlib.sha256).hexdigest()
    if expected_sig == provided_sig:
        return True
    return False
