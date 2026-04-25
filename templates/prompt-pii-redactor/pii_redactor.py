"""Prompt PII redactor.

Pre-flight scrubber for prompt content sent to a remote model. Replaces
common PII patterns with stable opaque tokens (e.g. <EMAIL_1>) so:

  * the model never sees raw PII
  * a downstream rehydrator can swap the tokens back in the model's
    response (for cases where the user does want to see their own PII
    echoed back, e.g. drafting an email).

Stdlib only. No external regex packs, no ML.

Detected entity types (conservative — bias is "miss rather than over-redact"):
  EMAIL          - RFC-ish email
  PHONE_US       - 10-digit US phone (with optional +1, separators)
  IPV4           - dotted-quad IPv4
  CREDIT_CARD    - 13-19 digit Luhn-valid sequence
  SSN_US         - NNN-NN-NNNN
  AWS_KEY_ID     - AKIA[A-Z0-9]{16}
  JWT            - 3-part base64url.dot.base64url.dot.base64url
  BEARER_TOKEN   - 'Bearer ' followed by 20+ url-safe chars

Returns (scrubbed_text, mapping) where mapping[token] = original.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Pattern

# ---- detectors -------------------------------------------------------------

EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
# US phone: optional +1, 3-3-4 with .,-, or space separators (or none).
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}(?!\d)"
)
IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\b"
)
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
AWS_KEY_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
JWT_RE = re.compile(
    r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b"
)
BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9_\-\.=]{20,}\b")
# Pre-filter: 13-19 consecutive digits, optionally separated by space or dash
# in groups. We Luhn-check before redacting to avoid eating order numbers.
CC_RE = re.compile(r"(?<!\d)(?:\d[\s-]?){12,18}\d(?!\d)")


def _luhn_ok(digits: str) -> bool:
    s = 0
    alt = False
    for ch in reversed(digits):
        if not ch.isdigit():
            return False
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        s += d
        alt = not alt
    return s % 10 == 0 and len(digits) >= 13


# ---- redactor --------------------------------------------------------------


@dataclass
class _Detector:
    label: str
    pattern: Pattern[str]
    luhn: bool = False


DETECTORS: list[_Detector] = [
    _Detector("EMAIL", EMAIL_RE),
    _Detector("JWT", JWT_RE),                # before BEARER_TOKEN: a JWT is more specific
    _Detector("BEARER_TOKEN", BEARER_RE),
    _Detector("AWS_KEY_ID", AWS_KEY_RE),
    _Detector("SSN_US", SSN_RE),
    _Detector("CREDIT_CARD", CC_RE, luhn=True),
    _Detector("PHONE_US", PHONE_RE),
    _Detector("IPV4", IPV4_RE),
]


def redact(text: str, detectors: Iterable[_Detector] = DETECTORS) -> tuple[str, dict[str, str]]:
    """Return (scrubbed_text, mapping_token_to_original)."""
    mapping: dict[str, str] = {}
    reverse: dict[str, str] = {}  # original -> token (so repeats reuse the same token)
    counters: dict[str, int] = {}

    out = text
    for det in detectors:
        def _sub(m: re.Match[str]) -> str:
            raw = m.group(0)
            if det.luhn:
                digits = re.sub(r"\D", "", raw)
                if not _luhn_ok(digits):
                    return raw  # not actually a credit card; leave alone
            if raw in reverse:
                return reverse[raw]
            counters[det.label] = counters.get(det.label, 0) + 1
            token = f"<{det.label}_{counters[det.label]}>"
            mapping[token] = raw
            reverse[raw] = token
            return token
        out = det.pattern.sub(_sub, out)
    return out, mapping


def rehydrate(text: str, mapping: dict[str, str]) -> str:
    """Replace tokens back with originals. Stable across rounds."""
    # Replace longest tokens first to avoid prefix collisions like
    # <EMAIL_1> vs <EMAIL_10>.
    for token in sorted(mapping.keys(), key=len, reverse=True):
        text = text.replace(token, mapping[token])
    return text
