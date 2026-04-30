import os
from cryptography.fernet import Fernet
key = os.environ["FERNET_KEY"].encode()
f = Fernet(key)

import hmac, hashlib
secret = os.environ["HMAC_SECRET"].encode()
mac = hmac.new(secret, b"payload", hashlib.sha256)

import jwt
token = jwt.encode({"sub": "u1"}, os.environ["JWT_SECRET"], algorithm="HS256")
