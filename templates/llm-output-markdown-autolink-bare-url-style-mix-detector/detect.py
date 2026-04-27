#!/usr/bin/env python3
"""Detect mixing of autolink style (<https://x>) and bare URL style (https://x)
within the same markdown document.

A consistent document should pick one: either all URLs are wrapped in angle
brackets as autolinks, or all are left bare. Mixing the two styles is a common
LLM output defect.

Exit 1 if both styles co-occur. Code/fenced regions are excluded.

Usage: detect.py FILE
"""
import re
import sys

URL_RE = re.compile(r'https?://[^\s<>\)\]]+')
AUTOLINK_RE = re.compile(r'<(https?://[^\s<>]+)>')


def strip_code(lines):
    out = []
    in_fence = False
    for line in lines:
        s = line.lstrip()
        if s.startswith('```') or s.startswith('~~~'):
            in_fence = not in_fence
            out.append('')
            continue
        if in_fence:
            out.append('')
            continue
        # strip inline code spans
        out.append(re.sub(r'`[^`]*`', '', line))
    return out


def find_inline_link_urls(text):
    """URLs inside [text](url) form — these are neither bare nor autolink."""
    urls = set()
    for m in re.finditer(r'\[[^\]]*\]\(([^)\s]+)', text):
        urls.add(m.group(1))
    return urls


def main(path):
    with open(path, encoding='utf-8') as f:
        raw = f.read()
    lines = strip_code(raw.splitlines())

    autolinks = []  # (lineno, url)
    bare = []       # (lineno, url)
    for i, line in enumerate(lines, 1):
        inline_urls = find_inline_link_urls(line)
        for m in AUTOLINK_RE.finditer(line):
            autolinks.append((i, m.group(1)))
        # find bare URLs not inside autolinks or inline links
        # Remove autolink occurrences first
        scrubbed = AUTOLINK_RE.sub('', line)
        # Remove inline link target portions
        scrubbed = re.sub(r'\[[^\]]*\]\([^)]*\)', '', scrubbed)
        for m in URL_RE.finditer(scrubbed):
            url = m.group(0).rstrip('.,;:!?')
            if url in inline_urls:
                continue
            bare.append((i, url))

    findings = 0
    if autolinks and bare:
        print(f"{path}: mixed URL styles — {len(autolinks)} autolink(s) and {len(bare)} bare URL(s)")
        for lineno, url in autolinks:
            print(f"  {path}:{lineno}: autolink <{url}>")
            findings += 1
        for lineno, url in bare:
            print(f"  {path}:{lineno}: bare {url}")
            findings += 1
        print(f"total findings: {findings}")
        return 1
    return 0


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("usage: detect.py FILE", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
