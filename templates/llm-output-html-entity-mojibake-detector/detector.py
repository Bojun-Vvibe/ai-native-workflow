#!/usr/bin/env python3
"""
llm-output-html-entity-mojibake-detector

Scans LLM output (markdown/plain text) for two failure modes:

1. Stray HTML entities that should have been decoded into real characters
   (e.g. "&amp;", "&#39;", "&lt;", "&nbsp;") leaking through into prose
   where the user clearly expected a literal "&", "'", "<", or space.

2. Mojibake patterns: a UTF-8 byte sequence that was decoded as Latin-1
   (or cp1252) and then re-encoded as UTF-8, producing tell-tale
   sequences like "â€™" (curly apostrophe), "â€œ"/"â€\x9d" (curly
   quotes), "Ã©" (e-acute), "Â " (no-break space), etc.

Reads from a file path argument, prints a JSON report to stdout.
Exit code 0 if clean, 1 if any issues found.

Stdlib only.
"""
import argparse
import json
import re
import sys

# Common HTML entities we expect to be decoded in finished prose.
# Numeric entities are caught by the regex below.
NAMED_ENTITY_RE = re.compile(
    r"&(amp|lt|gt|quot|apos|nbsp|copy|reg|trade|hellip|mdash|ndash|"
    r"lsquo|rsquo|ldquo|rdquo|bull|deg|plusmn|times|divide|"
    r"laquo|raquo|sect|para);"
)
NUMERIC_ENTITY_RE = re.compile(r"&#(?:x[0-9a-fA-F]+|[0-9]+);")

# Tell-tale mojibake fragments. These appear when UTF-8 bytes were
# decoded as Latin-1/cp1252 and then re-encoded as UTF-8.
MOJIBAKE_PATTERNS = [
    ("â€™", "U+2019 right single quote misencoded"),
    ("â€˜", "U+2018 left single quote misencoded"),
    ("â€œ", "U+201C left double quote misencoded"),
    ("â€\x9d", "U+201D right double quote misencoded"),
    ("â€”", "U+2014 em dash misencoded"),
    ("â€“", "U+2013 en dash misencoded"),
    ("â€¦", "U+2026 ellipsis misencoded"),
    ("Â ", "U+00A0 no-break space misencoded"),
    ("Ã©", "U+00E9 e-acute misencoded"),
    ("Ã¨", "U+00E8 e-grave misencoded"),
    ("Ã¢", "U+00E2 a-circumflex misencoded"),
    ("Ã­", "U+00ED i-acute misencoded"),
    ("Ã³", "U+00F3 o-acute misencoded"),
    ("Ãº", "U+00FA u-acute misencoded"),
    ("Ã±", "U+00F1 n-tilde misencoded"),
    ("ï»¿", "UTF-8 BOM as mojibake"),
]


def scan(text: str):
    issues = []
    lines = text.splitlines()
    for lineno, line in enumerate(lines, start=1):
        for m in NAMED_ENTITY_RE.finditer(line):
            issues.append({
                "kind": "stray_named_entity",
                "line": lineno,
                "col": m.start() + 1,
                "match": m.group(0),
                "hint": "Decode this HTML entity to its literal character.",
            })
        for m in NUMERIC_ENTITY_RE.finditer(line):
            issues.append({
                "kind": "stray_numeric_entity",
                "line": lineno,
                "col": m.start() + 1,
                "match": m.group(0),
                "hint": "Decode this numeric HTML entity to its literal character.",
            })
        for needle, why in MOJIBAKE_PATTERNS:
            start = 0
            while True:
                idx = line.find(needle, start)
                if idx == -1:
                    break
                issues.append({
                    "kind": "mojibake_sequence",
                    "line": lineno,
                    "col": idx + 1,
                    "match": needle,
                    "hint": why,
                })
                start = idx + len(needle)
    return issues


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path", help="Path to the LLM output file to scan.")
    args = p.parse_args(argv)

    with open(args.path, "r", encoding="utf-8") as fh:
        text = fh.read()

    issues = scan(text)
    report = {
        "path": args.path,
        "issue_count": len(issues),
        "issues": issues,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
