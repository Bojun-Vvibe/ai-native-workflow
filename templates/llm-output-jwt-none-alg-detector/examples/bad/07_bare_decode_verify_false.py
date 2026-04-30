from jwt import decode
data = decode(token, key, verify=False)
