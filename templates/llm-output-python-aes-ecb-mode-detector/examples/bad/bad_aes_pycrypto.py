from Crypto.Cipher import AES

key = b"0" * 16
cipher = AES.new(key, AES.MODE_ECB)
ct = cipher.encrypt(b"sixteen byte msg")
