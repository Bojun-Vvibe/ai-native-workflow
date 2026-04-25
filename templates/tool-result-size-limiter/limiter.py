"""tool-result-size-limiter

Cap the size of a tool result *before* it is concatenated into the
agent's next-turn context. Returns the original payload if it fits
under the byte budget; otherwise returns a head+tail "truncation
sandwich" with an inline marker line that names the bytes elided.

Stdlib only. Pure: never mutates input. Deterministic: same input
always produces the same output. Operates on the raw text, not on
characters or tokens, because the *budget* the caller cares about is
the byte cost of the eventual prompt assembly.

Two complementary mechanisms:

* **Whole-payload byte cap.** If `len(text.encode("utf-8")) <=
  max_bytes`, the original text is returned verbatim — no marker is
  added when the value already fits.
* **Head + tail sandwich.** Above the cap, the limiter keeps
  `head_ratio` of `max_bytes` from the start and the remainder from
  the end, joined by a single marker line of the form
  `\\n…<TRUNCATED:N bytes elided of M total, sha256=HEX12>…\\n`. The
  sha256 prefix is taken over the *elided* middle bytes so a skimming
  human (or a downstream tool) can tell whether two truncations had
  the same hidden payload — useful for "is this the same flaky log?"
  questions without exposing the contents.

UTF-8 boundary safety: head and tail are clipped on a UTF-8 character
boundary (never mid-codepoint) so the result is always valid UTF-8
even when the budget falls inside a multi-byte sequence.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


class SizeLimiterError(ValueError):
    """Raised on caller-side misuse (e.g. nonsensical budget)."""


@dataclass(frozen=True)
class LimitResult:
    text: str
    original_bytes: int
    output_bytes: int
    truncated: bool
    elided_bytes: int
    elided_sha256_prefix: str  # empty string when not truncated


def _safe_utf8_clip(b: bytes, n: int, *, from_end: bool) -> bytes:
    """Clip `b` to at most `n` bytes on a UTF-8 boundary.

    UTF-8 continuation bytes have the top two bits `10`. Walk inward
    until we land on a leading byte (top bit `0` for ASCII, or top
    two bits `11` for the start of a multi-byte sequence).
    """
    if n <= 0:
        return b""
    if n >= len(b):
        return b
    if from_end:
        # Clip the start: skip continuation bytes at the new start.
        start = len(b) - n
        while start < len(b) and (b[start] & 0xC0) == 0x80:
            start += 1
        return b[start:]
    else:
        # Clip the end: back off if the cut lands inside a sequence.
        end = n
        while end > 0 and (b[end] & 0xC0) == 0x80:
            end -= 1
        return b[:end]


def limit_tool_result(
    text: str,
    *,
    max_bytes: int,
    head_ratio: float = 0.6,
) -> LimitResult:
    """Cap `text` to `max_bytes` bytes; return a head+tail sandwich on overflow.

    Args:
        text: Tool output to size-cap. Must be `str`.
        max_bytes: Maximum total bytes (UTF-8) of the returned text,
            including the marker line. Must be >= 64 — any smaller
            and the marker itself would dominate the output.
        head_ratio: Fraction of `max_bytes` to spend on the head
            slice; the remainder (minus the marker) goes to the tail.
            Must be in `(0.0, 1.0)`.

    Returns:
        `LimitResult` with the (possibly truncated) text plus a small
        accounting record. `truncated=False` ⇒ output equals input.
    """
    if not isinstance(text, str):
        raise SizeLimiterError(f"text must be str, got {type(text).__name__}")
    if max_bytes < 64:
        raise SizeLimiterError(f"max_bytes must be >= 64, got {max_bytes}")
    if not 0.0 < head_ratio < 1.0:
        raise SizeLimiterError(
            f"head_ratio must be in (0.0, 1.0), got {head_ratio}"
        )

    raw = text.encode("utf-8")
    original = len(raw)

    if original <= max_bytes:
        return LimitResult(
            text=text,
            original_bytes=original,
            output_bytes=original,
            truncated=False,
            elided_bytes=0,
            elided_sha256_prefix="",
        )

    # Reserve ~120 bytes for the marker line. The marker length depends
    # on `elided_bytes` and `original`, so compute once with a placeholder
    # then once more with real numbers.
    head_budget = max(32, int(max_bytes * head_ratio))
    head_bytes = _safe_utf8_clip(raw, head_budget, from_end=False)

    # Tail gets whatever is left after head + marker reservation.
    marker_reserve = 120
    tail_budget = max(32, max_bytes - len(head_bytes) - marker_reserve)
    tail_bytes = _safe_utf8_clip(raw, tail_budget, from_end=True)

    # Make sure head and tail do not overlap (they won't here because
    # we are already in the > max_bytes branch and max_bytes < original,
    # but defend against pathological head_ratio anyway).
    elided_start = len(head_bytes)
    elided_end = original - len(tail_bytes)
    if elided_end <= elided_start:
        # Degenerate: tail and head together would cover the whole input.
        # Shrink the tail until they don't.
        tail_bytes = b""
        elided_end = original

    elided = raw[elided_start:elided_end]
    elided_n = len(elided)
    sha_prefix = hashlib.sha256(elided).hexdigest()[:12]
    marker = f"\n…<TRUNCATED:{elided_n} bytes elided of {original} total, sha256={sha_prefix}>…\n"
    marker_b = marker.encode("utf-8")

    out_b = head_bytes + marker_b + tail_bytes
    return LimitResult(
        text=out_b.decode("utf-8"),
        original_bytes=original,
        output_bytes=len(out_b),
        truncated=True,
        elided_bytes=elided_n,
        elided_sha256_prefix=sha_prefix,
    )
