from Crypto.Cipher import DES

key = b"0" * 8
cipher = DES.new(key, DES.MODE_ECB)
