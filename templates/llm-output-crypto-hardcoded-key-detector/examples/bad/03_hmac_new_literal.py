import hmac, hashlib
mac = hmac.new(b"hardcoded-secret-please-rotate", b"msg", hashlib.sha256)
