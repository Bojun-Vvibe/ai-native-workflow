from cryptography.hazmat.primitives.ciphers.aead import AESGCM
aead = AESGCM(b"thirty-two-byte-aesgcm-key-here!")
