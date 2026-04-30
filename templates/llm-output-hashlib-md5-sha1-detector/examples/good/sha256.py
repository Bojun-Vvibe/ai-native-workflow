import hashlib


def fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def integrity_tag(blob: bytes) -> str:
    return hashlib.sha512(blob).hexdigest()
