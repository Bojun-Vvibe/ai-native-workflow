"""Good fixture: signature verification explicitly enabled."""
import jwt


def parse(token: str, key: str) -> dict:
    return jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        options={"verify_signature": True, "verify_aud": True},
    )
