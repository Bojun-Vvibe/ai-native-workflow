"""Bad: hashlib digest comparison with ==."""
import hashlib


def verify_payload(payload: bytes, expected_digest: str) -> bool:
    return hashlib.sha256(payload).hexdigest() == expected_digest
