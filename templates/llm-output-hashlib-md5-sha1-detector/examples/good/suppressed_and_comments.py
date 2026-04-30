"""Ensure literals and suppressed lines do not trigger findings.

The string below contains the substring "hashlib.md5(" but is
inside a docstring, so it must not be flagged.
"""

import hashlib

# Documentation reference only: hashlib.sha1("x") in a comment.
NOTE = "hashlib.md5('x') would be wrong here"


def cache_bucket(key: str) -> int:
    # Non-security: pick a shard. Document the intent explicitly.
    return int(hashlib.md5(key.encode()).hexdigest()[:4], 16)  # weak-hash-ok


def cache_bucket_alt(key: str) -> int:
    return int(hashlib.sha1(key.encode()).hexdigest()[:4], 16)  # weak-hash-ok
