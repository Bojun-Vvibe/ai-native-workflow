#!/usr/bin/env python3
"""Detect shell-out and dynamic-eval sinks in CFML source.

See README.md for rationale and rules. python3 stdlib only.

Implementation note: CFML mixes tag syntax (`<cf...>`) with script
syntax inside `<cfscript>` blocks. We do *not* try to follow the
tag/script boundary -- we just blank comments and string-literal
contents and then run regexes line-by-line. The block-level CFML
comment `<!--- ... --->` is handled across lines via a small
state-machine pre-pass.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_SUPPRESS = re.compile(r"(?:<!---|//)\s*cfml-exec-ok\b")

RE_CFEXECUTE_TAG = re.compile(r"<\s*cfexecute\b", re.IGNORECASE)
RE_CFEXECUTE_SCRIPT = re.compile(r"\bcfexecute\s*\(", re.IGNORECASE)
RE_EVALUATE = re.compile(r"\bevaluate\s*\(", re.IGNORECASE)
RE_PRECISION = re.compile(r"\bprecisionEvaluate\s*\(", re.IGNORECASE)
RE_IIF = re.compile(r"\biif\s*\(", re.IGNORECASE)
RE_CFMODULE = re.compile(r"<\s*cfmodule\b", re.IGNORECASE)

# "dynamic" indicators -- only meaningful if found in the surviving
# (string-blanked) span on the same line.
RE_INTERP = re.compile(r"#[^#\n]+#")
RE_SCOPE = re.compile(
    r"\b(?:form|url|cgi|arguments|session|client|cookie|request)\.",
    re.IGNORECASE,
)


def strip_block_comments(text: str) -> str:
    """Blank `<!--- ... --->` block comments while preserving line
    breaks and column positions."""
    out = list(text)
    i = 0
    n = len(text)
    while i < n - 4:
        if text[i:i + 5] == "<!---":
            # Find closing `--->`.
            end = text.find("--->", i + 5)
            if end == -1:
                end = n
            else:
                end += 4
            for j in range(i, end):
                if out[j] != "\n":
                    out[j] = " "
            i = end
            continue
        i += 1
    return "".join(out)


def strip_line_comments_and_strings(line: str) -> str:
    """Blank `// ...EOL`, single-line `/* ... */` runs, and string
    literal contents on a single line."""
    n = len(line)
    out = list(line)
    i = 0
    in_str = ""  # "" | '"' | "'"
    while i < n:
        ch = out[i]
        if in_str:
            if ch == "\\" and i + 1 < n:
                out[i] = " "
                out[i + 1] = " "
                i += 2
                continue
            if ch == in_str:
                in_str = ""
                i += 1
                continue
            out[i] = " "
            i += 1
            continue
        # Not in string.
        if ch == "/" and i + 1 < n and out[i + 1] == "/":
            for j in range(i, n):
                out[j] = " "
            break
        if ch == "/" and i + 1 < n and out[i + 1] == "*":
            close = line.find("*/", i + 2)
            end = close + 2 if close != -1 else n
            for j in range(i, end):
                out[j] = " "
            i = end
            continue
        if ch in ('"', "'"):
            in_str = ch
            i += 1
            continue
        i += 1
    return "".join(out)


def is_dynamic(span: str) -> bool:
    return bool(RE_INTERP.search(span) or RE_SCOPE.search(span))


def is_cfml_file(path: Path) -> bool:
    return path.suffix.lower() in (".cfm", ".cfml", ".cfc")


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    orig_lines = text.splitlines()
    text = strip_block_comments(text)
    raw_lines = text.splitlines()
    for idx, raw in enumerate(raw_lines, start=1):
        # Suppression check uses the ORIGINAL line so the `<!--- ok --->`
        # token survives.
        orig = orig_lines[idx - 1] if idx - 1 < len(orig_lines) else raw
        if RE_SUPPRESS.search(orig):
            continue
        scrub = strip_line_comments_and_strings(raw)

        for pat, base in (
            (RE_CFEXECUTE_TAG, "cfml-cfexecute-tag"),
            (RE_CFEXECUTE_SCRIPT, "cfml-cfexecute-script"),
            (RE_PRECISION, "cfml-precision-evaluate"),
            (RE_EVALUATE, "cfml-evaluate"),
            (RE_IIF, "cfml-iif"),
            (RE_CFMODULE, "cfml-cfmodule"),
        ):
            for m in pat.finditer(scrub):
                # Heuristic span: from the sink to end of line *or*
                # to the matching `>` for tag-form, *or* to the
                # matching `)` for script-form. We approximate by
                # taking the rest of the scrubbed line; that is
                # enough to spot `#...#` and `scope.var`.
                span = scrub[m.start():]
                kind = base
                if is_dynamic(span):
                    kind = f"{base}-dynamic"
                # Special-case: `evaluate("1+1")` with a pure literal
                # body has no surviving content (we blanked the
                # string), so it stays as plain `cfml-evaluate`. That
                # is still risky enough to flag.
                findings.append(
                    (path, idx, m.start() + 1, kind, raw.strip())
                )
        # Avoid double-counting: `precisionEvaluate` also matches
        # `evaluate(`. De-dup by (line, col, kind-prefix).
    # Dedup pass: drop a `cfml-evaluate*` finding when an exactly-
    # overlapping `cfml-precision-evaluate*` finding exists at the
    # *same* start column - they describe the same source span.
    by_pos: dict[tuple[int, int], list[int]] = {}
    for i, (_p, line, col, _k, _s) in enumerate(findings):
        by_pos.setdefault((line, col), []).append(i)
    drop = set()
    for _pos, idxs in by_pos.items():
        kinds = [findings[i][3] for i in idxs]
        if any(k.startswith("cfml-precision-evaluate") for k in kinds):
            for i in idxs:
                if findings[i][3].startswith("cfml-evaluate"):
                    drop.add(i)
    return [f for i, f in enumerate(findings) if i not in drop]


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_cfml_file(sub):
                    yield sub
        elif p.is_file():
            yield p


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(f"usage: {argv[0]} <file_or_dir> [...]", file=sys.stderr)
        return 2
    total = 0
    for path in iter_targets(argv[1:]):
        for f_path, line, col, kind, snippet in scan_file(path):
            print(f"{f_path}:{line}:{col}: {kind} \u2014 {snippet}")
            total += 1
    print(f"# {total} finding(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
