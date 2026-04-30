import hashlib


def make_md5(data: bytes) -> str:
    h = hashlib.new("md5")
    h.update(data)
    return h.hexdigest()


def make_sha1_alt(data: bytes) -> str:
    h = hashlib.new("SHA-1")
    h.update(data)
    return h.hexdigest()
