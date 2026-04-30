import os
from Crypto.Cipher import AES

key = b"0" * 16
nonce = os.urandom(12)
cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
ct, tag = cipher.encrypt_and_digest(b"hello")
