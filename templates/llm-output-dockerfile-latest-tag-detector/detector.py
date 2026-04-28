#!/usr/bin/env python3
"""Detect Dockerfile FROM lines using :latest or no tag.

Stdlib only. Code-fence aware for Markdown input. Always exits 0.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterator, Tuple


FROM_RE = re.compile(r"^\s*FROM\s+(.+?)\s*$", re.IGNORECASE)
FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})\s*([A-Za-z0-9_+\-]*)\s*$")


def _iter_dockerfile_lines(text: str, is_markdown: bool) -> Iterator[Tuple[int, str]]:
    """Yield (1-indexed line number, line) for Dockerfile-relevant lines.

    For Markdown: only yield lines inside fenced code blocks tagged dockerfile.
    For raw Dockerfile: yield all lines.
    """
    if not is_markdown:
        for i, line in enumerate(text.splitlines(), start=1):
            yield i, line
        return

    in_fence = False
    fence_char = ""
    fence_len = 0
    fence_lang = ""
    for i, line in enumerate(text.splitlines(), start=1):
        m = FENCE_RE.match(line)
        if m and not in_fence:
            fence_char = m.group(2)[0]
            fence_len = len(m.group(2))
            fence_lang = m.group(3).lower()
            in_fence = True
            continue
        if in_fence and m:
            # potential closer: same char, length >= opener, no language
            if m.group(2)[0] == fence_char and len(m.group(2)) >= fence_len and not m.group(3):
                in_fence = False
                fence_lang = ""
                continue
        if in_fence and fence_lang in ("dockerfile",):
            yield i, line


def _looks_like_markdown(path: str, text: str) -> bool:
    if path.lower().endswith((".md", ".markdown")):
        return True
    # heuristic: contains a fenced code block opener
    return bool(re.search(r"(?m)^\s*```", text))


def _strip_platform_flags(rest: str) -> str:
    # Remove leading --platform=... --foo=... flags (BuildKit)
    parts = rest.split()
    out = [p for p in parts if not p.startswith("--")]
    return " ".join(out)


def _image_ref(rest: str) -> str:
    """Extract just the image reference (drop AS alias)."""
    rest = _strip_platform_flags(rest)
    # split off "AS alias"
    tokens = rest.split()
    if len(tokens) >= 3 and tokens[-2].upper() == "AS":
        return " ".join(tokens[:-2])
    return rest.strip()


def _classify(image_ref: str) -> Tuple[str, str] | None:
    """Return (code, message) if problematic, else None."""
    ref = image_ref.strip()
    if not ref:
        return None
    # digest pin -> always OK
    if "@sha256:" in ref or "@" in ref.split("/")[-1] and ":" in ref.split("@")[-1]:
        return None
    # template variable in tag region -> treat as pinned by build args
    last = ref.rsplit("/", 1)[-1]
    if "${" in last or last.startswith("$"):
        return None
    if ":" in last:
        tag = last.split(":", 1)[1]
        # if tag itself is a template var, treat as pinned
        if tag.startswith("${") or tag.startswith("$"):
            return None
        if tag.lower() == "latest":
            return ("DOCKER001", "image uses :latest tag")
        return None
    # no tag at all -> implicit latest
    return ("DOCKER002", "image has no tag (implicit :latest)")


def scan(path: str, text: str) -> int:
    is_md = _looks_like_markdown(path, text)
    findings = 0
    for lineno, line in _iter_dockerfile_lines(text, is_md):
        # skip comments
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        m = FROM_RE.match(line)
        if not m:
            continue
        rest = m.group(1)
        ref = _image_ref(rest)
        verdict = _classify(ref)
        if verdict is None:
            continue
        code, msg = verdict
        trimmed = line.strip()
        print(f"{path}:{lineno}: {code}: {msg} | {trimmed}")
        findings += 1
    print(f"# findings: {findings}")
    return findings


def _read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detector.py <path|-> [more paths...]", file=sys.stderr)
        print("# findings: 0")
        return 0
    for p in argv[1:]:
        display = p if p != "-" else "<stdin>"
        try:
            text = _read(p)
        except OSError as e:
            print(f"{display}: ERROR: {e}", file=sys.stderr)
            continue
        scan(display, text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
