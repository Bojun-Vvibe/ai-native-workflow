"""Good fixture: explicit allow-list, signature verified."""
import jwt


def parse(token: str, key: str) -> dict:
    return jwt.decode(token, key, algorithms=["HS256"])
