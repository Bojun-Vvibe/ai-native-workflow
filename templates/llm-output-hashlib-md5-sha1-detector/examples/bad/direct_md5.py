import hashlib


def fingerprint(token: str) -> str:
    return hashlib.md5(token.encode()).hexdigest()


def session_id(user_id: int, salt: bytes) -> str:
    return hashlib.md5(str(user_id).encode() + salt).hexdigest()
