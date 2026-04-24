#!/usr/bin/env python3
"""Canonical error-fingerprint hash for stuck-detection in repair loops.

Reads a JSON validator-error description on stdin (or from argv[1])
and prints a stable 16-hex-char fingerprint to stdout.

Input shape:
    {
      "error_class": "SchemaValidationError",
      "json_pointer": "/users/0/email",
      "expected": "string matching ^[^@]+@[^@]+\\.[^@]+$",
      "got": "not-an-email"          # ignored for fingerprinting
    }

Two errors fingerprint to the same hash iff they have the same
(error_class, normalised_pointer, expected). The actual offending
value is intentionally omitted so that "/users/0/email got
not-an-email" and "/users/1/email got also-bad" collapse to the
same fingerprint — they're the same mistake on two array elements.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from typing import Any


_ARRAY_INDEX_RE = re.compile(r"/\d+(?=/|$)")


def normalise_pointer(ptr: str) -> str:
    """Collapse numeric array indices in a JSON pointer to '*'.

    >>> normalise_pointer("/users/0/email")
    '/users/*/email'
    >>> normalise_pointer("/items/12/tags/3")
    '/items/*/tags/*'
    >>> normalise_pointer("/configs/redis/host")
    '/configs/redis/host'
    """
    return _ARRAY_INDEX_RE.sub("/*", ptr)


def fingerprint(err: dict[str, Any]) -> str:
    """Produce a 16-hex-char fingerprint of a validation error."""
    canonical = {
        "error_class": str(err.get("error_class", "UnknownError")),
        "json_pointer": normalise_pointer(str(err.get("json_pointer", "/"))),
        "expected": str(err.get("expected", "")),
    }
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _self_test() -> None:
    a = {"error_class": "SchemaValidationError",
         "json_pointer": "/users/0/email",
         "expected": "string matching ^[^@]+@[^@]+\\.[^@]+$",
         "got": "not-an-email"}
    b = {"error_class": "SchemaValidationError",
         "json_pointer": "/users/1/email",
         "expected": "string matching ^[^@]+@[^@]+\\.[^@]+$",
         "got": "also-bad"}
    c = {"error_class": "SchemaValidationError",
         "json_pointer": "/users/0/name",
         "expected": "string",
         "got": 42}
    assert fingerprint(a) == fingerprint(b), "array-index normalisation failed"
    assert fingerprint(a) != fingerprint(c), "different fields collided"
    # Pointer normalisation
    assert normalise_pointer("/a/0/b") == "/a/*/b"
    assert normalise_pointer("/a/12/b/3") == "/a/*/b/*"
    assert normalise_pointer("/a/b/c") == "/a/b/c"
    print("OK")


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] == "--self-test":
        _self_test()
        return 0
    raw = sys.stdin.read() if len(argv) == 1 else open(argv[1]).read()
    err = json.loads(raw)
    print(fingerprint(err))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
