from Crypto.Cipher import ChaCha20
c = ChaCha20.new(key=b"thirty-two-byte-chacha20-key-here", nonce=b"12345678")
