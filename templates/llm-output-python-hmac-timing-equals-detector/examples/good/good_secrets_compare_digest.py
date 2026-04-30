"""Good: uses secrets.compare_digest."""
import secrets


def check(submitted: str, expected: str) -> bool:
    # password equality, but constant-time
    return secrets.compare_digest(submitted, expected)
