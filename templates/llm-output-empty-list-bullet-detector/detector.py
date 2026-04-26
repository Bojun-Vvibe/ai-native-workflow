"""Pure-stdlib detector for empty Markdown list bullets in LLM output.

A common LLM artifact: the model plans an N-item list, emits the bullet
markers, and then either runs out of budget or "forgets" to fill some
items, leaving a literal `- ` or `* ` or `1.` line with nothing after
the marker. This survives every Markdown renderer (they happily render
an empty <li>) and survives most linters.

Three finding kinds:

- `empty_unordered_bullet` — `- `, `* `, or `+ ` followed by only
  whitespace (or nothing) until end of line.
- `empty_ordered_bullet`   — `<digit(s)>.` or `<digit(s)>)` followed
  by only whitespace.
- `whitespace_only_bullet` — bullet marker followed by ONLY
  whitespace characters that are not the empty string (a tab, an
  NBSP, etc.). Reported separately because it indicates the model
  tried to produce content and emitted invisible bytes.

Fenced code blocks (``` or ~~~) are skipped wholesale. Indentation
is preserved so a nested empty bullet still fires.

Usage:
    python3 detector.py [FILE ...]   # files, or stdin if none
    exit 0 = clean, exit 1 = findings (JSON on stdout)
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, asdict

FENCE_RE = re.compile(r"^\s*(```|~~~)")
UNORDERED_RE = re.compile(r"^(?P<indent>\s*)(?P<marker>[-*+])(?P<rest>.*)$")
ORDERED_RE = re.compile(r"^(?P<indent>\s*)(?P<marker>\d+[.)])(?P<rest>.*)$")

# Whitespace including NBSP, zero-width space, and assorted unicode spaces
# the model occasionally emits when it tries to "indent" inside a bullet.
INVISIBLE_WS = "\u00a0\u200b\u2000\u2001\u2002\u2003\u2009\u202f\u3000"


@dataclass(frozen=True)
class Finding:
    kind: str
    line_number: int
    marker: str
    raw_line: str

    def to_dict(self) -> dict:
        return asdict(self)


def _classify_rest(rest: str) -> str | None:
    """Return finding kind or None if the bullet has real content."""
    if rest == "":
        return "empty"
    # ASCII-only whitespace strip first (don't drop NBSP / ZWSP yet).
    ascii_stripped = rest.strip(" \t\r\n\v\f")
    if ascii_stripped == "":
        return "empty"
    # Anything left that is purely invisible / unicode whitespace?
    leftover = ascii_stripped
    for ch in INVISIBLE_WS:
        leftover = leftover.replace(ch, "")
    if leftover == "":
        return "whitespace_only"
    return None


def detect_empty_bullets(text: str) -> list[Finding]:
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
        m = UNORDERED_RE.match(raw)
        kind_prefix = "unordered"
        if not m:
            m = ORDERED_RE.match(raw)
            kind_prefix = "ordered"
        if not m:
            continue
        marker = m.group("marker")
        rest = m.group("rest")
        # Require that marker is followed by a space or EOL — otherwise it's
        # not a list item (e.g. "*emphasis*" or "1.5").
        if rest and not rest.startswith((" ", "\t")):
            continue
        # Drop the single separator space/tab so empty-rest is unambiguous
        body = rest[1:] if rest.startswith((" ", "\t")) else rest
        result = _classify_rest(body)
        if result is None:
            continue
        if result == "empty":
            kind = f"empty_{kind_prefix}_bullet"
        else:
            kind = "whitespace_only_bullet"
        findings.append(
            Finding(
                kind=kind,
                line_number=lineno,
                marker=marker,
                raw_line=raw,
            )
        )
    return findings


def format_report(findings: list[Finding]) -> str:
    if not findings:
        return "OK: no empty list bullets detected.\n"
    out = [f"FOUND {len(findings)} empty-bullet finding(s):"]
    for f in findings:
        out.append(
            f"  [{f.kind}] line={f.line_number} marker='{f.marker}' :: {f.raw_line!r}"
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
    findings = detect_empty_bullets(text)
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
