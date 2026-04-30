from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
c = Cipher(algorithms.AES(b"thirty-two-byte-static-aes-key!!"), modes.ECB())
