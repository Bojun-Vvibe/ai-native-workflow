"""Bad fixture: algorithms list contains 'none'."""
import jwt


def parse(token: str) -> dict:
    return jwt.decode(token, "anything", algorithms=["HS256", "none"])
