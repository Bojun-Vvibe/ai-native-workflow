# Known-answer test (KAT) for AES-ECB per NIST SP 800-38A appendix.
# This is a test fixture, not production crypto.
from Crypto.Cipher import AES
key = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
cipher = AES.new(key, AES.MODE_ECB)  # aes-ecb-ok: NIST KAT vector
