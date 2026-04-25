"""Pure language-mismatch detector for LLM outputs.

Decides whether a model response is plausibly in the *expected* natural
language script. Uses Unicode-block heuristics over the response's
non-whitespace, non-punctuation, non-digit characters — no models, no
network, no third-party deps.

Why this exists
---------------
A user prompts in English, the model answers in Chinese (or vice versa)
because earlier turns drifted, or because retrieved context was in
another language. Silent language drift breaks downstream consumers
(TTS, translation memory, regex extractors) and is invisible to a JSON
schema validator: the *shape* is correct, the *language* is wrong.

This detector returns one of four verdicts so the orchestrator can route:
    - ``match``           script majority is the expected family, no escalation
    - ``mixed``           expected family present but below ``min_ratio`` —
                          likely code-switched output; usually re-prompt
    - ``mismatch``        a different script family dominates — re-prompt or
                          fall back
    - ``insufficient``    fewer than ``min_chars`` classifiable characters
                          (e.g. pure JSON, code-only output) — caller decides

Hard rules
----------
- Pure stdlib (``unicodedata``, ``dataclasses``).
- No I/O, no clocks, no global mutable state.
- Unknown ``expected`` family raises ``LanguageConfigError`` at call time
  (silent default would defeat the gate).
- Whitespace, ASCII punctuation, digits, and emoji are *ignored* in the
  ratio denominator — they carry no language signal and would otherwise
  inflate "match" for a JSON-heavy CJK response.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Dict


class LanguageConfigError(ValueError):
    """Raised at call time for an unknown ``expected`` family or bad config."""


# Script families we classify. Keep this list small and stable — the point
# is "is the model answering in roughly the right script", not full
# language ID.
_FAMILIES = ("latin", "cjk", "cyrillic", "arabic", "devanagari", "hebrew", "greek")


def _classify_char(ch: str) -> str | None:
    """Return a family name for one character, or None if it should be ignored.

    Ignored characters: whitespace, ASCII punctuation, digits, symbols,
    control codes, and characters with no useful script signal.
    """
    cat = unicodedata.category(ch)
    # Skip categories that carry no language signal.
    # Z* = separators, P* = punctuation, N* = numbers, S* = symbols (incl. emoji),
    # C* = control / format / unassigned.
    if cat[0] in ("Z", "P", "N", "S", "C"):
        return None
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return None
    # unicodedata.name returns the canonical block-prefixed name.
    if name.startswith("LATIN"):
        return "latin"
    if name.startswith("CJK") or name.startswith("HIRAGANA") or name.startswith("KATAKANA") or name.startswith("HANGUL"):
        return "cjk"
    if name.startswith("CYRILLIC"):
        return "cyrillic"
    if name.startswith("ARABIC"):
        return "arabic"
    if name.startswith("DEVANAGARI"):
        return "devanagari"
    if name.startswith("HEBREW"):
        return "hebrew"
    if name.startswith("GREEK"):
        return "greek"
    return None


@dataclass
class DetectionResult:
    verdict: str                      # match | mixed | mismatch | insufficient
    expected: str
    dominant: str | None              # family with the highest count, or None
    expected_ratio: float             # expected family count / classified total
    classified_chars: int             # denominator
    counts: Dict[str, int] = field(default_factory=dict)
    reason: str = ""


def detect(
    text: str,
    expected: str,
    *,
    min_ratio: float = 0.7,
    min_chars: int = 20,
) -> DetectionResult:
    """Classify ``text`` against ``expected`` script family.

    Args:
        text: The model output.
        expected: One of ``_FAMILIES``.
        min_ratio: Minimum (expected_count / classified_total) to call ``match``.
            Below this but with expected_count > 0 → ``mixed``.
        min_chars: Minimum classified characters before any verdict other
            than ``insufficient`` is returned.
    """
    if expected not in _FAMILIES:
        raise LanguageConfigError(
            f"unknown expected family: {expected!r} (allowed: {_FAMILIES})"
        )
    if not (0.0 < min_ratio <= 1.0):
        raise LanguageConfigError(f"min_ratio must be in (0, 1], got {min_ratio}")
    if min_chars < 1:
        raise LanguageConfigError(f"min_chars must be >= 1, got {min_chars}")

    counts: Dict[str, int] = {fam: 0 for fam in _FAMILIES}
    classified = 0
    for ch in text:
        fam = _classify_char(ch)
        if fam is None:
            continue
        counts[fam] += 1
        classified += 1

    if classified < min_chars:
        return DetectionResult(
            verdict="insufficient",
            expected=expected,
            dominant=None,
            expected_ratio=0.0,
            classified_chars=classified,
            counts=counts,
            reason=f"only {classified} classifiable chars (need >= {min_chars})",
        )

    dominant = max(counts.items(), key=lambda kv: kv[1])[0]
    expected_count = counts[expected]
    ratio = expected_count / classified

    if ratio >= min_ratio:
        verdict = "match"
        reason = f"{expected_count}/{classified} = {ratio:.2f} >= {min_ratio}"
    elif expected_count > 0:
        verdict = "mixed"
        reason = (
            f"expected={expected_count}/{classified}={ratio:.2f} below "
            f"{min_ratio}; dominant={dominant}={counts[dominant]}"
        )
    else:
        verdict = "mismatch"
        reason = f"zero {expected} chars; dominant={dominant}={counts[dominant]}"

    return DetectionResult(
        verdict=verdict,
        expected=expected,
        dominant=dominant,
        expected_ratio=ratio,
        classified_chars=classified,
        counts=counts,
        reason=reason,
    )
