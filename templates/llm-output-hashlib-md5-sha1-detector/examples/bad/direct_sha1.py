import hashlib


def password_hash(password: str) -> str:
    # Wrong: SHA-1 is not a password KDF.
    return hashlib.sha1(password.encode()).hexdigest()


def integrity_tag(blob: bytes) -> str:
    return hashlib.sha1(blob).hexdigest()
