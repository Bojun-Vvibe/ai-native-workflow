import jwt
data = jwt.decode(token, key, options={"verify_signature": False})
