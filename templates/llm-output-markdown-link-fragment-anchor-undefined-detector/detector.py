#!/usr/bin/env python3
"""
llm-output-markdown-link-fragment-anchor-undefined-detector

For a single markdown document, find intra-document links of the form
`[text](#some-anchor)` whose `#some-anchor` does not resolve to any
heading inside the same document.

The anchor slug for a heading is computed using the GitHub-flavored
markdown convention:
  - lowercase the heading text
  - strip leading/trailing whitespace
  - replace runs of whitespace with a single hyphen
  - drop characters that are not alphanumeric, hyphen, or underscore
  - if the same slug appears multiple times, the second occurrence is
    suffixed with "-1", the third with "-2", etc.

Reads from a file path argument, prints a JSON report to stdout.
Exit code 0 if every intra-document anchor resolves, 1 otherwise.

Stdlib only.
"""
import argparse
import json
import re
import sys

ATX_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE_RE = re.compile(r"^(```|~~~)")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def slugify(text: str) -> str:
    # Strip markdown emphasis/code markers from heading text.
    text = re.sub(r"[`*_~]", "", text)
    text = text.strip().lower()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^a-z0-9\-_]", "", text)
    return text


def collect_headings(lines):
    """Yield (lineno, slug) for each ATX heading, skipping fenced code."""
    in_fence = False
    fence_marker = None
    seen = {}
    out = []
    for lineno, line in enumerate(lines, start=1):
        m_fence = FENCE_RE.match(line)
        if m_fence:
            marker = m_fence.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif fence_marker == marker:
                in_fence = False
                fence_marker = None
            continue
        if in_fence:
            continue
        m = ATX_HEADING_RE.match(line)
        if not m:
            continue
        base = slugify(m.group(2))
        if not base:
            continue
        count = seen.get(base, 0)
        slug = base if count == 0 else f"{base}-{count}"
        seen[base] = count + 1
        out.append((lineno, slug))
    return out


def collect_links(lines):
    """Yield (lineno, col, href, text) for every markdown link, skipping
    fenced code blocks."""
    in_fence = False
    fence_marker = None
    out = []
    for lineno, line in enumerate(lines, start=1):
        m_fence = FENCE_RE.match(line)
        if m_fence:
            marker = m_fence.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif fence_marker == marker:
                in_fence = False
                fence_marker = None
            continue
        if in_fence:
            continue
        for m in LINK_RE.finditer(line):
            out.append((lineno, m.start() + 1, m.group(2), m.group(1)))
    return out


def scan(text: str):
    lines = text.splitlines()
    headings = collect_headings(lines)
    slugs = {slug for _, slug in headings}
    issues = []
    for lineno, col, href, link_text in collect_links(lines):
        if not href.startswith("#"):
            continue
        anchor = href[1:]
        if not anchor:
            issues.append({
                "kind": "empty_fragment",
                "line": lineno,
                "col": col,
                "href": href,
                "text": link_text,
                "hint": "The fragment is empty (just '#').",
            })
            continue
        if anchor not in slugs:
            issues.append({
                "kind": "undefined_anchor",
                "line": lineno,
                "col": col,
                "href": href,
                "text": link_text,
                "hint": "No heading in this document slugs to that anchor.",
            })
    return {
        "headings": [{"line": ln, "slug": s} for ln, s in headings],
        "issues": issues,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path", help="Path to the markdown file to scan.")
    args = p.parse_args(argv)

    with open(args.path, "r", encoding="utf-8") as fh:
        text = fh.read()

    result = scan(text)
    report = {
        "path": args.path,
        "heading_count": len(result["headings"]),
        "issue_count": len(result["issues"]),
        "headings": result["headings"],
        "issues": result["issues"],
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if result["issues"] else 0


if __name__ == "__main__":
    sys.exit(main())
