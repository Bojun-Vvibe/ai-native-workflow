from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

key = b"0" * 16
cipher = Cipher(algorithms.AES(key), modes.ECB())
encryptor = cipher.encryptor()
