from Crypto.Cipher import AES
from Crypto.Cipher.AES import MODE_ECB

key = b"0" * 16
cipher = AES.new(key, MODE_ECB)
