#!/usr/bin/env python3
"""
llm-output-markdown-setext-vs-atx-heading-mix-detector

Pure-stdlib detector for the LLM markdown failure mode where a single
document mixes ATX-style headings (`# H1`, `## H2`) with Setext-style
headings (text underlined by `===` or `---`) for headings of the same
or comparable rank. Both styles are valid CommonMark, but mixing them
within one document:

- breaks markdownlint MD003 (heading-style),
- confuses TOC generators that assume one style,
- makes the raw markdown un-greppable for "all H2s in this doc".

Findings are emitted as one JSON object per line on stdout, sorted by
(line, kind) for byte-identical re-runs. Exit code is 1 if any finding
was emitted, else 0.

Finding kinds:
  - mixed_heading_style: document uses BOTH ATX and Setext headings
    for ranks present in both style families. Reported once per
    minority-style heading.
  - setext_h1_below_atx_h1: document already had an ATX `#` H1 and
    later introduces a Setext `===` H1 (or vice versa). Reported on
    the second-style occurrence.
  - setext_h2_below_atx_h2: same axis, H2 vs `---`.

Out of scope (handled by sister templates):
  - setext underline length validity (see
    llm-output-setext-heading-underline-length-validator),
  - skipped heading levels (see
    llm-output-markdown-heading-skip-level-detector),
  - trailing `#` on ATX (see
    llm-output-atx-heading-trailing-hash-detector).

Usage:
  python3 detector.py path/to/file.md
  cat file.md | python3 detector.py -
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, asdict
from typing import List, Optional


ATX_RE = re.compile(r"^(?P<hashes>#{1,6})(?:\s+\S|\s*$)")
# Setext underline: a line consisting only of = or - (length >= 1),
# preceded by a non-blank text line (the heading text).
SETEXT_EQ_RE = re.compile(r"^=+\s*$")
SETEXT_DASH_RE = re.compile(r"^-+\s*$")
FENCE_RE = re.compile(r"^(?P<f>`{3,}|~{3,})")


@dataclass(frozen=True)
class Finding:
    kind: str
    line: int  # 1-indexed
    style: str  # "atx" | "setext"
    rank: int  # 1 or 2 (setext only supports 1 and 2)
    text: str
    note: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, ensure_ascii=False)


def _strip_fenced_code_lines(lines: List[str]) -> List[bool]:
    """Return a parallel list[bool] marking each line as "inside fence"."""
    inside = [False] * len(lines)
    fence_char: Optional[str] = None
    fence_len = 0
    in_fence = False
    for i, line in enumerate(lines):
        m = FENCE_RE.match(line)
        if not in_fence and m:
            f = m.group("f")
            fence_char = f[0]
            fence_len = len(f)
            in_fence = True
            inside[i] = True  # the fence line itself is part of the block
            continue
        if in_fence:
            inside[i] = True
            # closing fence: same char, length >= opener
            if (
                fence_char is not None
                and line.lstrip().startswith(fence_char * fence_len)
                and set(line.strip()) == {fence_char}
            ):
                in_fence = False
                fence_char = None
                fence_len = 0
    return inside


@dataclass
class Heading:
    line: int  # 1-indexed
    style: str  # "atx" | "setext"
    rank: int
    text: str


def parse_headings(text: str) -> List[Heading]:
    lines = text.splitlines()
    inside_code = _strip_fenced_code_lines(lines)
    out: List[Heading] = []
    n = len(lines)
    i = 0
    while i < n:
        if inside_code[i]:
            i += 1
            continue
        line = lines[i]
        # ATX
        m = ATX_RE.match(line)
        if m:
            hashes = m.group("hashes")
            content = line[len(hashes):].strip().rstrip("#").strip()
            out.append(Heading(i + 1, "atx", len(hashes), content))
            i += 1
            continue
        # Setext: this line is non-blank and next line is === or ---
        if i + 1 < n and not inside_code[i + 1] and line.strip():
            nxt = lines[i + 1]
            if SETEXT_EQ_RE.match(nxt):
                out.append(Heading(i + 1, "setext", 1, line.strip()))
                i += 2
                continue
            if SETEXT_DASH_RE.match(nxt) and len(nxt.strip()) >= 2:
                # Require >=2 dashes to avoid colliding with thematic
                # break "---" (which CommonMark treats as <hr/> when on
                # its own line preceded by blank line). We still accept
                # 2+ dashes; a true thematic break is unambiguous only
                # when the previous line is blank, so we additionally
                # require the previous line to be blank to call it a
                # thematic break, otherwise it is a Setext H2.
                # If preceding line (lines[i]) is non-blank text, it's
                # a Setext H2.
                out.append(Heading(i + 1, "setext", 2, line.strip()))
                i += 2
                continue
        i += 1
    return out


def detect(text: str) -> List[Finding]:
    headings = parse_headings(text)
    findings: List[Finding] = []
    if not headings:
        return findings

    # Per-rank style buckets (ranks 1 and 2 only — Setext maxes at 2).
    by_rank = {1: {"atx": [], "setext": []}, 2: {"atx": [], "setext": []}}
    for h in headings:
        if h.rank in (1, 2):
            by_rank[h.rank][h.style].append(h)

    for rank in (1, 2):
        atx_list = by_rank[rank]["atx"]
        setext_list = by_rank[rank]["setext"]
        if atx_list and setext_list:
            # Mixed at this rank. Minority = whichever bucket is
            # smaller; tie -> setext is the minority (ATX is more
            # common in modern docs).
            if len(atx_list) < len(setext_list):
                minority = atx_list
                majority_style = "setext"
            else:
                minority = setext_list
                majority_style = "atx"
            for h in minority:
                findings.append(
                    Finding(
                        kind="mixed_heading_style",
                        line=h.line,
                        style=h.style,
                        rank=h.rank,
                        text=h.text,
                        note=(
                            f"document mixes ATX and Setext H{rank} headings; "
                            f"majority style is '{majority_style}'"
                        ),
                    )
                )

            # Order-aware bonus signal: did setext appear AFTER atx for
            # this rank (or vice versa)? Reported on the second-style
            # heading's first occurrence.
            first_atx = atx_list[0].line
            first_setext = setext_list[0].line
            if rank == 1:
                kind = "setext_h1_below_atx_h1"
            else:
                kind = "setext_h2_below_atx_h2"
            if first_atx < first_setext:
                h = setext_list[0]
                findings.append(
                    Finding(
                        kind=kind,
                        line=h.line,
                        style="setext",
                        rank=rank,
                        text=h.text,
                        note=(
                            f"Setext H{rank} appears after an earlier ATX H{rank} "
                            f"on line {first_atx}"
                        ),
                    )
                )
            elif first_setext < first_atx:
                h = atx_list[0]
                findings.append(
                    Finding(
                        kind=kind,
                        line=h.line,
                        style="atx",
                        rank=rank,
                        text=h.text,
                        note=(
                            f"ATX H{rank} appears after an earlier Setext H{rank} "
                            f"on line {first_setext}"
                        ),
                    )
                )

    findings.sort(key=lambda f: (f.line, f.kind))
    return findings


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("usage: detector.py <path|->", file=sys.stderr)
        return 2
    src = argv[1]
    if src == "-":
        text = sys.stdin.read()
    else:
        with open(src, "r", encoding="utf-8") as f:
            text = f.read()
    findings = detect(text)
    for f in findings:
        print(f.to_json())
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
