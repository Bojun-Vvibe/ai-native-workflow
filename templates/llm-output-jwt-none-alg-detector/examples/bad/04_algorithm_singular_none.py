import jwt
data = jwt.decode(token, key, algorithm="none")
