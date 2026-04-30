from cryptography.hazmat.primitives.ciphers import Cipher, algorithms
from cryptography.hazmat.primitives.ciphers.modes import ECB

key = b"0" * 16
cipher = Cipher(algorithms.AES(key), ECB())
