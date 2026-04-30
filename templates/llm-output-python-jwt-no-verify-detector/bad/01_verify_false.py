"""Bad fixture: PyJWT decode with verify=False (PyJWT < 2.x footgun)."""
import jwt


def read_user(token: str, key: str) -> dict:
    # LLM-emitted: "just decode the JWT, ignore the signature"
    return jwt.decode(token, key, verify=False)
