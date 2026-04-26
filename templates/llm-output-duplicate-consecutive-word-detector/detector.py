"""Pure-stdlib detector for duplicate consecutive words in LLM prose output.

A common LLM artifact is the "the the", "is is", "and and" stutter — usually
a sampling glitch at a token boundary. The duplicates survive grammar checkers
because each word is individually valid, and they survive Markdown linters
because they are not a structural issue. This detector scans line-by-line and
flags any case where the same alphabetic word appears twice in a row
(case-insensitive), excluding fenced code blocks and inline code spans.

Usage:
    python3 detector.py [FILE ...]   # read named files; stdin if none
    exit 0 = clean, exit 1 = findings (JSON on stdout)

Pure function: no I/O inside `detect_duplicates`. Read-only; no repair.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, asdict
from typing import Iterable, Iterator

# Words that legitimately repeat in English / technical prose. Tuning is
# deliberately conservative — false negatives are cheaper than false positives
# in a CI gate.
ALLOWLIST_PAIRS = frozenset(
    {
        ("had", "had"),
        ("that", "that"),
        ("is", "is"),  # "what it is is unclear" — leave it; flagging breeds fatigue
        ("blah", "blah"),
        ("yada", "yada"),
        ("ha", "ha"),
        ("bye", "bye"),
    }
)

WORD_RE = re.compile(r"[A-Za-z]+(?:[''][A-Za-z]+)?")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


@dataclass(frozen=True)
class Finding:
    kind: str
    line_number: int
    column: int
    word: str
    context: str

    def to_dict(self) -> dict:
        return asdict(self)


def _strip_inline_code(line: str) -> str:
    # Replace inline code spans with spaces of equal length so columns stay
    # meaningful for any callers who care.
    return INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), line)


def detect_duplicates(text: str) -> list[Finding]:
    if not isinstance(text, str):
        raise TypeError("text must be str")
    findings: list[Finding] = []
    in_fence = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        line = _strip_inline_code(raw)
        prev_word: str | None = None
        prev_end = 0
        for m in WORD_RE.finditer(line):
            word = m.group(0)
            lw = word.lower()
            if prev_word is not None and lw == prev_word:
                # Check there is only whitespace between them — not punctuation.
                between = line[prev_end : m.start()]
                if between.strip() == "" and (lw, lw) not in ALLOWLIST_PAIRS:
                    ctx_lo = max(0, prev_end - 20)
                    ctx_hi = min(len(raw), m.end() + 20)
                    findings.append(
                        Finding(
                            kind="duplicate_consecutive_word",
                            line_number=lineno,
                            column=m.start() + 1,
                            word=word,
                            context=raw[ctx_lo:ctx_hi].strip(),
                        )
                    )
            prev_word = lw
            prev_end = m.end()
    return findings


def format_report(findings: list[Finding]) -> str:
    if not findings:
        return "OK: no duplicate consecutive words detected.\n"
    out = [f"FOUND {len(findings)} duplicate-word finding(s):"]
    for f in findings:
        out.append(
            f"  [line={f.line_number} col={f.column}] '{f.word} {f.word}' :: ...{f.context}..."
        )
    return "\n".join(out) + "\n"


def _read_inputs(argv: list[str]) -> str:
    if len(argv) <= 1:
        return sys.stdin.read()
    chunks = []
    for path in argv[1:]:
        with open(path, "r", encoding="utf-8") as fh:
            chunks.append(fh.read())
    return "\n".join(chunks)


def main(argv: list[str]) -> int:
    text = _read_inputs(argv)
    findings = detect_duplicates(text)
    payload = {
        "findings": [f.to_dict() for f in findings],
        "count": len(findings),
        "ok": len(findings) == 0,
    }
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
