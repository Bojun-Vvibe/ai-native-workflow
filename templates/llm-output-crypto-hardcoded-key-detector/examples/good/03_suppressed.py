from cryptography.fernet import Fernet
# legacy fixture; tracked elsewhere
f = Fernet(b"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")  # crypto-key-ok
