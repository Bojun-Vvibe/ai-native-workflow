import jwt
data = jwt.decode(token, key, algorithms=["HS256"])
data2 = jwt.decode(token, key, algorithms=["RS256"], options={"verify_signature": True})
