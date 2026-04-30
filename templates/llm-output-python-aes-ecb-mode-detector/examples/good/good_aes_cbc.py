import os
from Crypto.Cipher import AES

key = b"0" * 16
iv = os.urandom(16)
cipher = AES.new(key, AES.MODE_CBC, iv=iv)
