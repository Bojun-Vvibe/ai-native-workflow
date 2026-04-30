import os
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

key = b"0" * 32
nonce = os.urandom(16)
cipher = Cipher(algorithms.AES(key), modes.CTR(nonce))
