from hashlib import md5, sha1


def signature(payload: bytes, key: bytes) -> str:
    return md5(payload + key).hexdigest()


def short_id(payload: bytes) -> str:
    return sha1(payload).hexdigest()
