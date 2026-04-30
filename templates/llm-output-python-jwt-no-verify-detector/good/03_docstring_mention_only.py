"""Good fixture: docstring mentions verify=False but it is not code.

This file's docstring contains the literal phrase ``verify=False``
intentionally to confirm the detector ignores text inside string
literals. The active code path uses an explicit algorithm allow-list.
"""
import jwt


def parse(token: str, key: str) -> dict:
    return jwt.decode(token, key, algorithms=["ES256"])
