"""
agent-system-prompt-instruction-conflict-detector
=================================================

Pure stdlib detector for *internal* contradictions in an agent's
system prompt — the failure mode where the prompt accumulates over
months of "just one more rule" edits until it contains, somewhere,
both:

    "Always cite the source URL for every claim."
    "Never include URLs in your response — they break our renderer."

The model picks one of the two at random per call (sometimes
per-paragraph), and the team spends two weeks blaming "model drift"
before someone re-reads the prompt.

This detector finds three classes of conflict by extracting the
*imperative clauses* in the prompt — sentences whose normalized
predicate matches both a polarity-flipping pair and at least one
shared content-word. It is deliberately a structural lexical
detector, not an LLM judge: the *value* of the structural detector is
that it produces the same answer at 03:00 as at 15:00 and runs in
50 ms in CI, so a regression-introducing prompt edit is caught at
review time, not after a week of degraded responses.

Conflict classes:

  - polarity_conflict :
        one clause says ALWAYS X, another says NEVER X (or
        equivalent: must / must not, do / do not, use / do not use,
        include / do not include, etc).

  - quantifier_conflict :
        one clause says ALWAYS X, another says SOMETIMES / WHEN
        <condition> X — a soft contradiction that produces
        non-deterministic behavior. Lower-severity than polarity
        because the second clause may be a *refinement* if it shares
        a condition word; the detector flags it and lets the caller
        decide.

  - format_conflict :
        two clauses prescribe *different specific values* for the
        same surface — "respond in markdown" vs "respond in plain
        text", "use bullet lists" vs "use numbered lists". Detected
        by recognizing a small, extensible enum of prescription
        targets (`format`, `tone`, `length`, `language`).

Hard rule: pure function over a string. No I/O, no clocks. Caller
decides whether to fail CI, surface as a warning, or block the prompt
revision.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set, Tuple


# Polarity markers. Order matters: longer / more specific first so
# "do not" matches before "do".
_NEG_MARKERS = (
    "never",
    "do not",
    "don't",
    "must not",
    "must never",
    "should not",
    "shouldn't",
    "avoid",
    "refuse to",
    "do not ever",
)
_POS_MARKERS = (
    "always",
    "must",
    "must always",
    "should",
    "be sure to",
    "make sure to",
    "ensure you",
    "ensure that you",
    "you must",
    "you should",
    "you always",
    "you will",
)
_QUANT_MARKERS = (
    "sometimes",
    "occasionally",
    "when appropriate",
    "if appropriate",
    "when relevant",
    "when needed",
    "when necessary",
    "where possible",
)

# Tiny stoplist — the content-word overlap test is doing the work,
# so we only strip the most common function words and the imperative
# markers themselves.
_STOPWORDS = frozenset(
    """
    a an the and or but if then else for of in on at to from with
    by as is are was were be been being am do does did
    you your yours we our ours i me my mine us they them their theirs
    it its this that these those there here so than too very just
    will would shall should can could may might
    not no
    """.split()
)

# Format-conflict prescription targets and their value enums. A clause
# matches a target if it contains the target keyword AND at least one
# value from the enum; a conflict is two matching clauses with
# *different* values from the same enum.
_FORMAT_TARGETS: Dict[str, Tuple[str, ...]] = {
    "format": ("markdown", "plain text", "json", "yaml", "html", "xml"),
    "list_style": ("bullet", "bulleted", "numbered", "ordered list", "unordered list"),
    "tone": ("formal", "informal", "casual", "professional", "playful", "concise", "verbose"),
    "language": ("english", "spanish", "french", "chinese", "japanese", "german"),
    "length": ("one sentence", "short", "long", "brief", "detailed", "comprehensive"),
}


@dataclass(frozen=True)
class Clause:
    line_index: int       # 1-based
    text: str             # original sentence
    polarity: str         # "pos" | "neg" | "quant" | "neutral"
    predicate_tokens: Tuple[str, ...]  # content tokens used for overlap


@dataclass(frozen=True)
class Finding:
    kind: str
    severity: str         # "high" | "medium"
    detail: str
    clause_a_line: int
    clause_a_text: str
    clause_b_line: int
    clause_b_text: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Report:
    clause_count: int
    findings: List[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def to_dict(self) -> dict:
        tally: Dict[str, int] = {}
        for f in self.findings:
            tally[f.kind] = tally.get(f.kind, 0) + 1
        return {
            "ok": self.ok,
            "clause_count": self.clause_count,
            "finding_kind_totals": dict(sorted(tally.items())),
            "findings": [
                f.to_dict()
                for f in sorted(
                    self.findings,
                    key=lambda x: (x.kind, x.clause_a_line, x.clause_b_line),
                )
            ],
        }


def _split_sentences(text: str) -> List[Tuple[int, str]]:
    """
    Return list of (line_index_1based, sentence_text). A "sentence"
    is a clause ending at `.`, `!`, `?`, or end-of-line. We split
    line-by-line so the report can quote a 1-based line number.
    """
    out: List[Tuple[int, str]] = []
    for li, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        # crude sentence split that doesn't try to be smart about
        # abbreviations; system prompts rarely have "Dr." mid-rule.
        parts = re.split(r"(?<=[.!?])\s+", stripped)
        for p in parts:
            p = p.strip().rstrip(".!?")
            if p:
                out.append((li, p))
    return out


def _classify_polarity(sentence: str) -> Tuple[str, Optional[str]]:
    """
    Return (polarity, matched_marker). Polarity in
    {"pos", "neg", "quant", "neutral"}.
    """
    s = " " + sentence.lower() + " "
    for m in _NEG_MARKERS:
        if f" {m} " in s or s.startswith(f" {m} ") or s.startswith(f"{m} "):
            return "neg", m
    for m in _POS_MARKERS:
        if f" {m} " in s or s.startswith(f" {m} ") or s.startswith(f"{m} "):
            return "pos", m
    for m in _QUANT_MARKERS:
        if f" {m} " in s or s.startswith(f" {m} ") or s.startswith(f"{m} "):
            return "quant", m
    return "neutral", None


def _content_tokens(sentence: str, exclude_marker: Optional[str]) -> Tuple[str, ...]:
    """
    Lowercased content tokens for overlap matching. Strips stopwords,
    the matched polarity marker (so "always cite urls" and "never cite
    urls" overlap on {"cite","urls"}), and trims punctuation.
    """
    s = sentence.lower()
    if exclude_marker:
        s = s.replace(exclude_marker, " ")
    # split on non-alpha runs
    raw = re.findall(r"[a-z][a-z\-]*", s)
    out = []
    for w in raw:
        if w in _STOPWORDS or len(w) < 3:
            continue
        # naive singularization: "urls" -> "url", "claims" -> "claim",
        # "boxes" -> "box". Keeps "ss" endings (class, address)
        # untouched. Good enough for the lexical-overlap test we are
        # doing here; not a real stemmer.
        if w.endswith("ies") and len(w) > 4:
            w = w[:-3] + "y"
        elif w.endswith("es") and len(w) > 4 and not w.endswith("ses"):
            w = w[:-2]
        elif w.endswith("s") and not w.endswith("ss") and len(w) > 3:
            w = w[:-1]
        out.append(w)
    return tuple(out)


def _build_clauses(text: str) -> List[Clause]:
    out: List[Clause] = []
    for li, sent in _split_sentences(text):
        polarity, marker = _classify_polarity(sent)
        tokens = _content_tokens(sent, marker)
        out.append(
            Clause(
                line_index=li,
                text=sent,
                polarity=polarity,
                predicate_tokens=tokens,
            )
        )
    return out


def _overlap_score(a: Tuple[str, ...], b: Tuple[str, ...]) -> Tuple[int, Set[str]]:
    sa, sb = set(a), set(b)
    inter = sa & sb
    return len(inter), inter


def _format_target_match(sent: str) -> List[Tuple[str, str]]:
    """
    Returns list of (target, value) the sentence makes a prescription
    on. A sentence can prescribe multiple targets.
    """
    s = sent.lower()
    out: List[Tuple[str, str]] = []
    for target, values in _FORMAT_TARGETS.items():
        target_word = target.replace("_", " ")
        # Heuristic: target keyword appears OR a value appears with a
        # prescriptive verb ("respond in markdown" — no "format" word
        # but "respond" + value is enough).
        target_present = (
            target_word in s
            or "respond" in s
            or "reply" in s
            or "answer" in s
            or "write" in s
            or "use" in s
            or "speak" in s
        )
        if not target_present:
            continue
        for v in values:
            if v in s:
                out.append((target, v))
                break  # one value per target per sentence
    return out


def detect(prompt_text: str, *, min_overlap: int = 2) -> Report:
    """
    Detect internal conflicts in *prompt_text*. `min_overlap` is the
    minimum number of shared content tokens for a polarity or
    quantifier conflict to fire — 2 is the default because a single
    shared token (e.g. "always cite sources" vs "never cite headers")
    is too weak.
    """
    if not isinstance(prompt_text, str):
        raise TypeError("detect() expects str")

    clauses = _build_clauses(prompt_text)
    findings: List[Finding] = []

    # Polarity + quantifier conflicts: pairwise scan over imperative
    # clauses only (neutral clauses can't conflict with anything).
    imperatives = [c for c in clauses if c.polarity in ("pos", "neg", "quant")]
    for i in range(len(imperatives)):
        for j in range(i + 1, len(imperatives)):
            a, b = imperatives[i], imperatives[j]
            count, shared = _overlap_score(a.predicate_tokens, b.predicate_tokens)
            if count < min_overlap:
                continue
            polarities = frozenset({a.polarity, b.polarity})
            if polarities == {"pos", "neg"}:
                findings.append(Finding(
                    kind="polarity_conflict",
                    severity="high",
                    detail=(
                        f"clauses share {count} content tokens "
                        f"({sorted(shared)}) but opposite polarities"
                    ),
                    clause_a_line=a.line_index,
                    clause_a_text=a.text,
                    clause_b_line=b.line_index,
                    clause_b_text=b.text,
                ))
            elif polarities == {"pos", "quant"} or polarities == {"neg", "quant"}:
                findings.append(Finding(
                    kind="quantifier_conflict",
                    severity="medium",
                    detail=(
                        f"clauses share {count} content tokens "
                        f"({sorted(shared)}) but mix absolute and "
                        f"conditional quantifiers"
                    ),
                    clause_a_line=a.line_index,
                    clause_a_text=a.text,
                    clause_b_line=b.line_index,
                    clause_b_text=b.text,
                ))

    # Format conflicts: per-target, are there two clauses with
    # different values?
    target_to_clauses: Dict[str, List[Tuple[Clause, str]]] = {}
    for c in clauses:
        for target, value in _format_target_match(c.text):
            target_to_clauses.setdefault(target, []).append((c, value))

    for target, entries in target_to_clauses.items():
        # Find pairs with distinct values.
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                ca, va = entries[i]
                cb, vb = entries[j]
                if va == vb:
                    continue
                findings.append(Finding(
                    kind="format_conflict",
                    severity="high",
                    detail=(
                        f"target='{target}' prescribed both "
                        f"'{va}' and '{vb}'"
                    ),
                    clause_a_line=ca.line_index,
                    clause_a_text=ca.text,
                    clause_b_line=cb.line_index,
                    clause_b_text=cb.text,
                ))

    return Report(clause_count=len(clauses), findings=findings)


def _cli() -> int:
    """
    Read prompt text from stdin or argv[1], print JSON report. Exit 0
    if ok, 1 if findings, 2 on malformed input.
    """
    try:
        if len(sys.argv) > 1 and sys.argv[1] != "-":
            with open(sys.argv[1], "r", encoding="utf-8") as fh:
                text = fh.read()
        else:
            text = sys.stdin.read()
    except OSError as e:
        print(json.dumps({"error": f"io: {e}"}), file=sys.stderr)
        return 2

    report = detect(text)
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(_cli())
