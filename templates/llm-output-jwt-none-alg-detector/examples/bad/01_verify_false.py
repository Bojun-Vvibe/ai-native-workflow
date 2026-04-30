import jwt
data = jwt.decode(token, key, verify=False)
