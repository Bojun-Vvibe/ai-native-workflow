import jwt
data = jwt.decode(token, key, algorithms=["HS256", "none"])
