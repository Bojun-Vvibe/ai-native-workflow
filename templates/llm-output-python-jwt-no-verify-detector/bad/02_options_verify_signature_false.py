"""Bad fixture: options dict disables verify_signature."""
import jwt


def parse(token: str, key: str) -> dict:
    return jwt.decode(
        token,
        key,
        algorithms=["HS256"],
        options={"verify_signature": False},
    )
