import jwt as JWT

def whoami(token, key):
    # algorithms list explicitly includes 'none' — accepts forged tokens.
    return JWT.decode(token, key, algorithms=["HS256", "none"])
