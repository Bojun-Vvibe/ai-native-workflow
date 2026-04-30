from Crypto.Cipher import DES3

key = b"0" * 24
cipher = DES3.new(key, DES3.MODE_ECB)
