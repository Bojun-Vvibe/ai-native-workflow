import hashlib


def short_id(blob: bytes) -> str:
    return hashlib.blake2b(blob, digest_size=16).hexdigest()


def derive_key(password: bytes, salt: bytes) -> bytes:
    # PBKDF2 is the right primitive for password->key derivation.
    return hashlib.pbkdf2_hmac("sha256", password, salt, 200_000)
