"""Pure prompt-injection prefilter for untrusted text fragments.

The problem: an agent stitches retrieved-document text, tool output, or user
input into the prompt sent to an LLM. If that text contains instructions
("ignore previous instructions and...", "</system>", "you are now..."), the
LLM may obey them. This module is a *pre*-filter — it scans text BEFORE it
is concatenated into the prompt and returns a structured verdict the
caller can branch on. It does not call any model.

Design choices:

- Severity is a small ordered enum: clean < suspicious < blocked. The caller
  decides what to do at each level (allow / wrap-in-quote-fence / drop).
- Detectors are pure regex / substring rules; each rule has a stable id so
  log analysis can grep "rule_id=role_override_attempt" cleanly. Adding a
  rule never reorders existing rule ids.
- Default action of an *unrecognised* high-risk pattern is suspicious, NOT
  blocked. Blocking is reserved for things that are unambiguously hostile
  (e.g. literal `</system>` close tags, "ignore previous/all" verbs in an
  imperative position). A noisy blocker is worse than a noisy flagger
  because callers learn to override blocks.
- The redactor returns a NEW string with detected spans replaced by a
  stable token (`[REDACTED:role_override_attempt]`). Spans never overlap;
  the highest-severity, then earliest, then longest match wins.

No I/O, no clocks. Stdlib-only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Iterable


class Severity(IntEnum):
    CLEAN = 0
    SUSPICIOUS = 1
    BLOCKED = 2


@dataclass(frozen=True)
class Rule:
    rule_id: str
    pattern: re.Pattern
    severity: Severity
    note: str


@dataclass(frozen=True)
class Hit:
    rule_id: str
    severity: Severity
    start: int
    end: int
    matched_text: str


@dataclass
class Verdict:
    severity: Severity
    hits: list[Hit] = field(default_factory=list)
    redacted_text: str = ""

    def to_jsonable(self) -> dict:
        return {
            "severity": self.severity.name.lower(),
            "hit_count": len(self.hits),
            "rule_ids": sorted({h.rule_id for h in self.hits}),
            "hits": [
                {
                    "rule_id": h.rule_id,
                    "severity": h.severity.name.lower(),
                    "start": h.start,
                    "end": h.end,
                }
                for h in self.hits
            ],
        }


def _ci(pat: str) -> re.Pattern:
    return re.compile(pat, re.IGNORECASE | re.DOTALL)


# Rule order here is the order new rules are appended; rule_ids are the
# stable contract, never reorder.
DEFAULT_RULES: tuple[Rule, ...] = (
    Rule(
        "role_override_attempt",
        _ci(r"\bignore\s+(?:all\s+)?(?:the\s+)?(?:previous|prior|above)\s+(?:instructions?|prompts?|rules?)\b"),
        Severity.BLOCKED,
        "Classic 'ignore previous instructions' jailbreak verb.",
    ),
    Rule(
        "system_tag_close",
        _ci(r"</\s*(?:system|assistant|tool|developer)\s*>"),
        Severity.BLOCKED,
        "Literal close tag for a privileged role envelope.",
    ),
    Rule(
        "system_tag_open",
        _ci(r"<\s*(?:system|developer)\s*>"),
        Severity.BLOCKED,
        "Literal open tag for a privileged role envelope.",
    ),
    Rule(
        "you_are_now",
        _ci(r"\byou\s+are\s+now\s+(?:a|an|the)\s+\w+"),
        Severity.SUSPICIOUS,
        "Persona-swap framing; common but not always hostile.",
    ),
    Rule(
        "exfiltrate_secrets",
        _ci(r"\b(?:print|reveal|show|leak|dump|output)\s+(?:your\s+)?(?:system\s+prompt|instructions|api[\s_-]?key|secret)s?\b"),
        Severity.BLOCKED,
        "Direct exfiltration request for prompt or credentials.",
    ),
    Rule(
        "tool_call_inject",
        _ci(r"<\s*tool[_\s-]?call\b[^>]*>"),
        Severity.BLOCKED,
        "Tool-call envelope smuggled inside untrusted text.",
    ),
    Rule(
        "url_then_imperative",
        _ci(r"https?://\S+\s+(?:then|and)\s+(?:run|execute|exec|delete|remove|rm)\b"),
        Severity.SUSPICIOUS,
        "URL followed by an imperative verb — common phishing-via-doc pattern.",
    ),
    Rule(
        "base64_blob_long",
        re.compile(r"(?:[A-Za-z0-9+/]{60,}={0,2})"),
        Severity.SUSPICIOUS,
        "Long base64-looking blob; may smuggle hidden instructions.",
    ),
)


def scan(text: str, rules: Iterable[Rule] = DEFAULT_RULES) -> list[Hit]:
    """Return all rule hits in `text`. Hits may overlap; resolution is the
    redactor's job.
    """
    hits: list[Hit] = []
    for rule in rules:
        for m in rule.pattern.finditer(text):
            hits.append(
                Hit(
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                    start=m.start(),
                    end=m.end(),
                    matched_text=m.group(0),
                )
            )
    return hits


def _resolve_overlapping(hits: list[Hit]) -> list[Hit]:
    """Pick a non-overlapping subset. Priority: severity desc, start asc,
    length desc. This is greedy (interval-scheduling is overkill for the
    typical 0-10 hit count and would re-rank by length-only).
    """
    if not hits:
        return []
    ranked = sorted(hits, key=lambda h: (-int(h.severity), h.start, -(h.end - h.start)))
    chosen: list[Hit] = []
    for h in ranked:
        if any(not (h.end <= c.start or h.start >= c.end) for c in chosen):
            continue
        chosen.append(h)
    chosen.sort(key=lambda h: h.start)
    return chosen


def redact(text: str, hits: list[Hit]) -> str:
    chosen = _resolve_overlapping(hits)
    if not chosen:
        return text
    out: list[str] = []
    cursor = 0
    for h in chosen:
        out.append(text[cursor:h.start])
        out.append(f"[REDACTED:{h.rule_id}]")
        cursor = h.end
    out.append(text[cursor:])
    return "".join(out)


def evaluate(text: str, rules: Iterable[Rule] = DEFAULT_RULES) -> Verdict:
    """Top-level pure entry point. Returns a Verdict.

    The Verdict's severity is the MAX severity across all hits.
    """
    hits = scan(text, rules)
    if not hits:
        return Verdict(severity=Severity.CLEAN, hits=[], redacted_text=text)
    worst = max(h.severity for h in hits)
    return Verdict(
        severity=worst,
        hits=sorted(hits, key=lambda h: h.start),
        redacted_text=redact(text, hits),
    )
