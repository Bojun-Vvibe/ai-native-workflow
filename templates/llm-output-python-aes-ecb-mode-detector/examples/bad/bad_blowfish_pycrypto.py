from Crypto.Cipher import Blowfish

key = b"0" * 16
cipher = Blowfish.new(key, Blowfish.MODE_ECB)
