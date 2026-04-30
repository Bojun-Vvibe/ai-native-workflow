"""Bad fixture: options dict disables verify_aud and verify_exp."""
import jwt


def parse(token: str, key: str) -> dict:
    return jwt.decode(
        token,
        key,
        algorithms=["HS256"],
        options={"verify_aud": False, "verify_exp": False},
    )
