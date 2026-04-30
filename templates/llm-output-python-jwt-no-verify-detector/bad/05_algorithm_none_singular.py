"""Bad fixture: algorithm='none' (singular kwarg)."""
import jwt


def make(payload: dict) -> str:
    return jwt.encode(payload, key="", algorithm="None")
