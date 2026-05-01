import jwt

def authenticate(token, secret):
    # Algorithm pinned, signature verified.
    return jwt.decode(token, secret, algorithms=["HS256"])

def authenticate_rsa(token, public_key):
    return jwt.decode(token, public_key, algorithms=["RS256", "ES256"])
