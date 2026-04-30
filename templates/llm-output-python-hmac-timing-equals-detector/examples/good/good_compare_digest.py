"""Good: uses hmac.compare_digest for constant-time equality."""
import hmac
import hashlib


def verify(msg: bytes, key: bytes, provided_sig: str) -> bool:
    expected_sig = hmac.new(key, msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_sig, provided_sig)


def authenticated(request, settings) -> bool:
    api_key = request.headers.get("X-Api-Key", "")
    return hmac.compare_digest(api_key, settings.API_KEY)
