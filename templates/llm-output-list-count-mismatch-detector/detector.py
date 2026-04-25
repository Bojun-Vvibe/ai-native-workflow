"""Detect when an LLM's enumerated list output does not match the count it promised.

Catches the failure mode where the prompt asks for "5 reasons" and the model returns:

  * 3 bullets (under-delivery — the most common case; usually means the model ran out
    of useful things to say but didn't admit it),
  * 7 bullets (over-delivery — the model padded with restatements),
  * the right *count* of bullets but with one obviously truncated mid-sentence
    (the trailing bullet ends without terminal punctuation and is markedly shorter
    than the others — a common artifact of hitting `max_tokens` mid-stream),
  * "5 reasons" promised but no enumerated list at all (the model wrote prose).

Pure stdlib (`re`, `dataclasses`). Pure function over two strings (the prompt and the
output). No I/O, no clocks. Sortable findings for cron-friendly diffing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- promise extraction ---------------------------------------------------

# Spelled-out small numbers we want to recognize. Capping at 20 keeps the surface
# small and matches the realistic prompt-shape "give me N things" for N <= 20.
_NUMBER_WORDS: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
}

# "5 reasons", "five reasons", "list of 7 X", "exactly 3 ...", "top 4 ..."
# Word-boundary anchored on both sides so "in 25 minutes" does NOT match.
_PROMISE_RE = re.compile(
    r"\b(?:list of|top|exactly|provide|give|name|enumerate|return)?\s*"
    r"(\d{1,3}|" + "|".join(_NUMBER_WORDS.keys()) + r")\b"
    r"\s+(?:reasons?|items?|bullets?|points?|steps?|examples?|ways?|tips?|things?|options?|ideas?"
    r"|advantages?|disadvantages?|benefits?|drawbacks?|failure modes?|modes?|causes?|approaches?"
    r"|techniques?|patterns?|practices?|rules?|principles?|strategies?|methods?)",
    re.IGNORECASE,
)


def extract_promised_count(prompt: str) -> int | None:
    """Return the largest count promised in the prompt, or None.

    "Largest" — because prompts often say "give me at least 5 ... up to 10" and
    the floor is the contract we should hold the model to weakly, but the ceiling
    is the contract we should never exceed. We pick the *first* match for stability;
    operators reading findings need predictability more than they need cleverness.
    """
    m = _PROMISE_RE.search(prompt)
    if not m:
        return None
    raw = m.group(1).lower()
    if raw.isdigit():
        return int(raw)
    return _NUMBER_WORDS.get(raw)


# --- list extraction ------------------------------------------------------

# Recognized bullet shapes:
#   - "1. foo"      ordered numeric
#   - "1) foo"
#   - "- foo"       unordered
#   - "* foo"
#   - "• foo"
# A bullet line begins at start-of-line (after optional whitespace) and the marker
# is followed by exactly one space and then content.
_BULLET_RE = re.compile(r"^\s{0,3}(?:(\d+)[.)]|[-*\u2022])\s+(.+?)\s*$")


@dataclass(frozen=True)
class Bullet:
    line_no: int  # 1-indexed
    ordinal: int | None  # explicit number for "1. foo"; None for "- foo"
    text: str


def extract_bullets(output: str) -> list[Bullet]:
    bullets: list[Bullet] = []
    for i, line in enumerate(output.splitlines(), start=1):
        m = _BULLET_RE.match(line)
        if not m:
            continue
        ordinal = int(m.group(1)) if m.group(1) else None
        text = m.group(2)
        bullets.append(Bullet(i, ordinal, text))
    return bullets


# --- truncation heuristic -------------------------------------------------

_TERMINAL_PUNCT = {".", "!", "?", '."', '!"', '?"', ".)", "!)", "?)", ".]", "!]", "?]"}


_STOP_WORDS = {"and", "or", "the", "a", "an", "to", "of", "with", "in", "for", "by", "on", "at", "as", "is", "are", "was", "were", "be"}


def looks_truncated(b: Bullet, peers: list[Bullet]) -> bool:
    """A bullet is *suspected* truncated when it is the LAST bullet AND lacks terminal
    punctuation AND (ends with a stop-word / dangling-comma OR is markedly shorter
    than its peers).

    Two-arm signal:
      - Lexical: "...lets clients hint **and**" — no model would write a complete
        bullet ending in "and"; the only generator of that pattern is `max_tokens`
        cutting mid-clause.
      - Geometric: length < 60% of median peer length — the model started a bullet
        and ran out of budget before saying anything substantive.
    Either arm is enough; both must pass the punctuation+last-position prefilter.
    """
    if not peers or peers[-1] is not b:
        return False
    if any(b.text.rstrip().endswith(p) for p in _TERMINAL_PUNCT):
        return False

    last_token = b.text.split()[-1] if b.text.split() else ""
    lexical_signal = bool(
        last_token and (last_token.endswith(",") or last_token.lower() in _STOP_WORDS)
    )

    other_lens = [len(p.text) for p in peers if p is not b]
    geometric_signal = False
    if other_lens:
        other_lens.sort()
        median = other_lens[len(other_lens) // 2]
        if median > 0 and len(b.text) < 0.6 * median:
            geometric_signal = True

    return lexical_signal or geometric_signal


# --- ordinal-skip heuristic -----------------------------------------------

def find_ordinal_skips(bullets: list[Bullet]) -> list[str]:
    """Return human-readable descriptions of ordinal skips.

    If the first numeric bullet is `n`, the rest must be n+1, n+2, ... — gaps are
    a finding ("the model wrote `1. ... 2. ... 4. ...`"). Mixed numeric+unordered
    bullets are not gaps; we only check the *numeric subsequence*.
    """
    out: list[str] = []
    numbered = [b for b in bullets if b.ordinal is not None]
    if len(numbered) < 2:
        return out
    expected = numbered[0].ordinal + 1
    assert expected is not None
    for b in numbered[1:]:
        assert b.ordinal is not None
        if b.ordinal != expected:
            out.append(f"ordinal jumped from {expected - 1} to {b.ordinal} at line {b.line_no}")
            expected = b.ordinal + 1
        else:
            expected += 1
    return out


# --- top-level report -----------------------------------------------------

@dataclass
class ListCountReport:
    promised: int | None
    delivered: int
    findings: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        # Closed enum: clean / under / over / no_list_promised_was_made / no_promise / truncated_tail / ordinal_gap
        # When multiple apply, the *most actionable* wins (under and truncated both → truncated_tail
        # because that tells the operator "raise max_tokens", which fixes both).
        if self.promised is None:
            return "no_promise"
        if self.delivered == 0:
            return "no_list_promised_was_made"
        if any(f.startswith("truncated_tail") for f in self.findings):
            return "truncated_tail"
        if any(f.startswith("ordinal_gap") for f in self.findings):
            return "ordinal_gap"
        if self.delivered < self.promised:
            return "under"
        if self.delivered > self.promised:
            return "over"
        return "clean"


def detect(prompt: str, output: str) -> ListCountReport:
    promised = extract_promised_count(prompt)
    bullets = extract_bullets(output)
    findings: list[str] = []

    if promised is not None:
        if not bullets:
            findings.append(f"no_list: prompt promised {promised} items but output has zero bullets")
        else:
            if len(bullets) < promised:
                findings.append(f"under_delivery: promised {promised}, delivered {len(bullets)}")
            elif len(bullets) > promised:
                findings.append(f"over_delivery: promised {promised}, delivered {len(bullets)}")
            if looks_truncated(bullets[-1], bullets):
                findings.append(
                    f"truncated_tail: last bullet at line {bullets[-1].line_no} "
                    f"ends without terminal punctuation and is markedly shorter than peers"
                )
    for desc in find_ordinal_skips(bullets):
        findings.append(f"ordinal_gap: {desc}")

    findings.sort()
    return ListCountReport(promised=promised, delivered=len(bullets), findings=findings)
