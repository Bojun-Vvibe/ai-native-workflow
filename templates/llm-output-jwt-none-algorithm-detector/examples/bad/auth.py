import jwt

# Missing algorithms kwarg entirely → permissive verifier.
def authenticate(token, secret):
    payload = jwt.decode(token, secret)
    return payload["sub"]

# Explicit verify=False — signature never checked.
def parse_only(token):
    return jwt.decode(token, options={"verify_signature": False})
