"""Bad fixture: algorithms=None bypasses allow-list."""
import jwt


def parse(token: str, key: str) -> dict:
    return jwt.decode(token, key, algorithms=None)
