"""model-output-truncation-detector — heuristic detector for outputs
cut off at max_tokens, plus a continuation-prompt builder.

When an LLM hits its `max_tokens` budget mid-thought, the API
typically returns `finish_reason="length"`. That signal is necessary
but not sufficient: it tells you *the limit was hit*, not whether
the response *needed* more tokens. And many wrappers swallow
finish_reason entirely, leaving you with a string that ends with
", and then the user should " and no metadata.

This template provides:

  * `detect(text, finish_reason=None)` -> TruncationVerdict
        Combines the (optional) finish_reason signal with structural
        heuristics on the text itself: dangling code fences, unclosed
        brackets, mid-sentence stop, mid-list stop, mid-bullet stop.
  * `build_continuation_prompt(verdict, original_request, partial)`
        Returns a prompt the caller can send back to the model to
        resume generation. The prompt:
          - tells the model exactly where it stopped (last 200 chars)
          - reminds it of the original task
          - instructs it to **continue without restating** what it
            already produced

Heuristics are deliberately conservative: when finish_reason is
explicitly "stop", structural anomalies are downgraded to a warning
rather than an "almost certainly truncated" verdict, because models
legitimately produce odd-looking endings (a code block that ends a
file, a bullet list that ends a section).

The classification levels are:

    TRUNCATED        finish_reason=length, OR very-strong structural signals
    LIKELY_TRUNCATED multiple weak signals with no explicit "stop"
    SUSPICIOUS       one weak signal, finish_reason absent
    CLEAN            finish_reason=stop and no anomalies

Caller decides what to do with each level. Most production loops
treat TRUNCATED and LIKELY_TRUNCATED as "send a continuation",
SUSPICIOUS as "log and move on", CLEAN as "ship it."
"""

from __future__ import annotations

import dataclasses
import re
from typing import Literal

Verdict = Literal["CLEAN", "SUSPICIOUS", "LIKELY_TRUNCATED", "TRUNCATED"]


@dataclasses.dataclass(frozen=True)
class TruncationVerdict:
    verdict: Verdict
    signals: tuple[str, ...]
    finish_reason: str | None
    tail: str  # last 200 chars, for logging / continuation prompts


# Patterns
_OPEN_FENCE = re.compile(r"```")
_SENTENCE_END = re.compile(r"[.!?\"')\]]\s*$")
_BULLET_LINE = re.compile(r"^\s*([-*+]|\d+\.)\s+")


def _bracket_balance(text: str) -> dict[str, int]:
    pairs = {"(": ")", "[": "]", "{": "}"}
    stack: list[str] = []
    in_str: str | None = None
    escape = False
    for ch in text:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if in_str:
            if ch == in_str:
                in_str = None
            continue
        if ch in ('"', "'"):
            in_str = ch
            continue
        if ch in pairs:
            stack.append(ch)
        elif ch in pairs.values():
            if stack and pairs[stack[-1]] == ch:
                stack.pop()
            # else: stray close — we ignore for truncation purposes
    return {"unclosed_open": len(stack)}


def _ends_mid_word(text: str) -> bool:
    stripped = text.rstrip()
    if not stripped:
        return False
    # Mid-word: last char is a letter and not preceded by punctuation
    # within the last 80 chars. Avoid flagging legitimate sentence
    # endings ending in a non-period (lists, code).
    if not stripped[-1].isalpha():
        return False
    # If there is a sentence terminator in the last 40 chars, probably fine
    tail = stripped[-40:]
    return not _SENTENCE_END.search(tail)


def _ends_mid_bullet(text: str) -> bool:
    lines = text.splitlines()
    if len(lines) < 2:
        return False
    last = lines[-1]
    prev = lines[-2]
    # Last line is a bullet line with very short content (<3 words)
    if _BULLET_LINE.match(last):
        content = _BULLET_LINE.sub("", last).strip()
        if len(content.split()) < 3:
            return True
    # Or last char of last line is mid-word AND previous line was a bullet
    if _BULLET_LINE.match(prev) and _ends_mid_word(last):
        return True
    return False


def detect(text: str, finish_reason: str | None = None) -> TruncationVerdict:
    """Classify whether `text` looks truncated.

    `finish_reason` is the upstream signal if available
    ("stop", "length", "content_filter", "tool_calls", or None).
    """
    signals: list[str] = []

    # Structural signals
    if _OPEN_FENCE.findall(text).__len__() % 2 == 1:
        signals.append("unclosed_code_fence")

    bal = _bracket_balance(text)
    if bal["unclosed_open"] > 0:
        signals.append(f"unclosed_brackets={bal['unclosed_open']}")

    if _ends_mid_word(text):
        signals.append("ends_mid_word")

    if _ends_mid_bullet(text):
        signals.append("ends_mid_bullet")

    if text and not text.endswith(("\n",)) and len(text) > 50:
        # Not a strong signal on its own; we count it only if combined
        # with another anomaly, handled below.
        pass

    tail = text[-200:]

    # Verdict
    if finish_reason == "length":
        return TruncationVerdict("TRUNCATED", tuple(signals) or ("finish_reason=length",), finish_reason, tail)

    strong = {"unclosed_code_fence"}
    has_strong = any(s in strong for s in signals)
    n = len(signals)

    if finish_reason == "stop":
        # Trust the stop signal. Downgrade structural signals.
        if has_strong:
            return TruncationVerdict("SUSPICIOUS", tuple(signals), finish_reason, tail)
        return TruncationVerdict("CLEAN", (), finish_reason, tail)

    # finish_reason is None or some other value
    if has_strong and n >= 2:
        return TruncationVerdict("TRUNCATED", tuple(signals), finish_reason, tail)
    if has_strong or n >= 2:
        return TruncationVerdict("LIKELY_TRUNCATED", tuple(signals), finish_reason, tail)
    if n == 1:
        return TruncationVerdict("SUSPICIOUS", tuple(signals), finish_reason, tail)
    return TruncationVerdict("CLEAN", (), finish_reason, tail)


def build_continuation_prompt(
    verdict: TruncationVerdict,
    original_request: str,
    partial: str,
    *,
    max_tail_chars: int = 200,
) -> str:
    """Build a follow-up prompt asking the model to resume generation.

    Critical: instructs the model NOT to restate. The most common
    failure mode of naive continuation is the model re-emitting its
    last 100 tokens, which both wastes budget and produces a stitch
    seam the caller has to detect and remove.
    """
    if verdict.verdict == "CLEAN":
        raise ValueError("nothing to continue: verdict is CLEAN")
    tail = partial[-max_tail_chars:]
    return (
        "Your previous response was cut off mid-output.\n"
        f"Detected signals: {', '.join(verdict.signals) or '(none)'}\n"
        f"finish_reason was: {verdict.finish_reason!r}\n\n"
        "Original request:\n"
        "---\n"
        f"{original_request}\n"
        "---\n\n"
        "The exact last characters you produced were:\n"
        "---\n"
        f"{tail}\n"
        "---\n\n"
        "Resume from exactly that point. Do NOT restate, summarize, "
        "or apologize. Output only the continuation, starting with "
        "the very next character that should follow the tail above. "
        "If you were inside a code block, stay inside it; if a "
        "sentence was mid-word, finish the word."
    )
