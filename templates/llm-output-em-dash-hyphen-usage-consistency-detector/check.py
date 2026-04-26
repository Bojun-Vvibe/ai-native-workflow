#!/usr/bin/env python3
"""
llm-output-em-dash-hyphen-usage-consistency-detector

Detects mixed/inconsistent dash usage in prose:
  - em dash  (U+2014, "—")  used as a parenthetical break
  - en dash  (U+2013, "–")  used for ranges
  - double hyphen ("--")    ASCII stand-in for em dash
  - spaced hyphen (" - ")   ASCII stand-in for em dash

Mixing these in the same document is a tell-tale sign that an LLM stitched
together text from sources with different typographic conventions.

Reads markdown / plain text from stdin or argv[1]. Fenced code blocks and
inline code spans are stripped to avoid false positives on CLI examples
(e.g. `--flag`).

Exit code: 0 if at most one dash convention is used, 1 if two or more.
"""
from __future__ import annotations

import re
import sys

EM_DASH = "\u2014"   # —
EN_DASH = "\u2013"   # –


def strip_code(text: str) -> str:
    """Remove fenced code blocks and inline code spans."""
    out_lines = []
    in_fence = False
    fence_marker = ""
    for line in text.splitlines():
        stripped = line.lstrip()
        if not in_fence and (stripped.startswith("```") or stripped.startswith("~~~")):
            in_fence = True
            fence_marker = stripped[:3]
            continue
        if in_fence and stripped.startswith(fence_marker):
            in_fence = False
            continue
        if not in_fence:
            out_lines.append(line)
    body = "\n".join(out_lines)
    # Strip inline code spans `...`
    body = re.sub(r"`[^`\n]*`", "", body)
    return body


def find_examples(text: str, pattern: str, limit: int = 3) -> list[str]:
    """Return up to `limit` short context snippets containing pattern."""
    out = []
    for m in re.finditer(re.escape(pattern), text):
        start = max(0, m.start() - 20)
        end = min(len(text), m.end() + 20)
        snippet = text[start:end].replace("\n", " ")
        out.append(snippet)
        if len(out) >= limit:
            break
    return out


def analyze(text: str) -> dict:
    cleaned = strip_code(text)

    em_count = cleaned.count(EM_DASH)
    en_count = cleaned.count(EN_DASH)
    # Double hyphen used as dash (not part of a long string of -----).
    double_hyphen_matches = re.findall(r"(?<!-)--(?!-)", cleaned)
    double_hyphen_count = len(double_hyphen_matches)
    # Spaced hyphen as dash: " - " between word characters.
    spaced_hyphen_matches = re.findall(r"\w \- \w", cleaned)
    spaced_hyphen_count = len(spaced_hyphen_matches)

    conventions = {
        "em_dash": em_count,
        "en_dash": en_count,
        "double_hyphen": double_hyphen_count,
        "spaced_hyphen": spaced_hyphen_count,
    }
    used = {k: v for k, v in conventions.items() if v > 0}

    samples = {
        "em_dash": find_examples(cleaned, EM_DASH),
        "en_dash": find_examples(cleaned, EN_DASH),
    }
    return {
        "counts": conventions,
        "distinct_used": sorted(used.keys()),
        "samples": samples,
    }


def main() -> int:
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = sys.stdin.read()

    result = analyze(text)
    counts = result["counts"]
    used = result["distinct_used"]

    print(f"em_dash      (\u2014) count: {counts['em_dash']}")
    print(f"en_dash      (\u2013) count: {counts['en_dash']}")
    print(f"double_hyphen (--)  count: {counts['double_hyphen']}")
    print(f"spaced_hyphen ( - ) count: {counts['spaced_hyphen']}")
    print(f"distinct conventions used: {used}")

    if len(used) <= 1:
        print("status: OK (single dash convention)")
        return 0

    print(f"status: FAIL (mixed dash conventions: {len(used)})")
    if result["samples"]["em_dash"]:
        print("  em_dash examples:")
        for s in result["samples"]["em_dash"]:
            print(f"    ...{s}...")
    if result["samples"]["en_dash"]:
        print("  en_dash examples:")
        for s in result["samples"]["en_dash"]:
            print(f"    ...{s}...")
    return 1


if __name__ == "__main__":
    sys.exit(main())
