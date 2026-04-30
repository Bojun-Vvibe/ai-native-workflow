import jwt
token = jwt.encode({"sub": "u1"}, "literal-jwt-signing-secret", algorithm="HS256")
