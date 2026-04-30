# Comment that mentions AES.MODE_ECB and modes.ECB() should not be flagged.
# Bad: AES.new(key, AES.MODE_ECB)
"This string literal mentions AES.MODE_ECB but is data, not code."
import os
from Crypto.Cipher import AES
key = b"0" * 16
cipher = AES.new(key, AES.MODE_GCM, nonce=os.urandom(12))
