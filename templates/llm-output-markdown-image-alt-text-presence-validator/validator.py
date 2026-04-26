"""Pure-stdlib detector for missing / placeholder markdown image alt text.

Markdown image syntax ``![alt](url)`` puts the alt text between the
brackets. LLMs routinely emit one of three failure modes:

1. Empty alt text: ``![](https://example.com/diagram.png)`` — accessible
   to no screen reader, no fallback when the image fails to load.
2. Placeholder alt text: ``![image](url)``, ``![alt](url)``, ``![todo](url)``,
   ``![](url)`` after a regenerate-pass left the bracket intentionally empty.
3. Alt text that is just the filename: ``![diagram.png](url)`` — a tell
   that the model copied the URL's basename in lieu of describing the image.

This template enforces **alt-text presence and informativeness**, not
length or grammar. It does not call a vision model. It does not try to
auto-fill alt text. It is a gate, not a fixer.

Three finding kinds:

- ``empty_alt`` — the bracket between ``![`` and ``](`` is empty or
  whitespace-only.
- ``placeholder_alt`` — alt text matches a curated, lowercase
  placeholder list (``image``, ``alt``, ``picture``, ``img``,
  ``screenshot``, ``todo``, ``tbd``, ``placeholder``, ``figure``).
- ``filename_as_alt`` — alt text equals the URL's last path segment
  (case-insensitive), or strips to a single bare filename like
  ``diagram.png`` / ``screenshot-2024-01-01.jpg``.

Reference-style images (``![alt][ref]``) and HTML ``<img>`` tags are
intentionally **out of scope**: reference-style images get caught by
the link-reference orphan detector; HTML ``<img>`` is a separate
parser concern (raw HTML mixed into markdown).

Pure function: no I/O, no markdown parser dependency, no network.
Findings are sorted by ``(line, column, kind)`` for deterministic
CI diffing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List


class ValidationError(ValueError):
    """Raised when ``text`` is not a ``str``."""


@dataclass(frozen=True)
class Finding:
    kind: str
    line: int  # 1-indexed
    column: int  # 1-indexed, position of the leading '!' of the image
    raw: str  # the alt text as written (empty string for empty_alt)
    detail: str


# Inline image: ![alt](url). Non-greedy alt; URL stops at the first
# unescaped close paren or whitespace+title. Reference-style and HTML
# <img> are intentionally not matched.
_IMAGE_RE = re.compile(
    r"!\[(?P<alt>[^\]\n]*)\]\((?P<url>[^)\s]+)(?:\s+\"[^\"]*\")?\)"
)
_FENCE_RE = re.compile(r"^[ \t]*(```|~~~)")

_PLACEHOLDERS = frozenset(
    {
        "image",
        "alt",
        "picture",
        "img",
        "screenshot",
        "todo",
        "tbd",
        "placeholder",
        "figure",
    }
)

_FILENAME_RE = re.compile(
    r"^[\w\-.]+\.(?:png|jpe?g|gif|svg|webp|bmp|tiff?|ico|pdf)$",
    re.IGNORECASE,
)


def _basename(url: str) -> str:
    # Strip query string and fragment, then take the last path component.
    cut = url.split("?", 1)[0].split("#", 1)[0]
    if "/" in cut:
        return cut.rsplit("/", 1)[-1]
    return cut


def validate_image_alt_text(text: str) -> List[Finding]:
    """Return findings for images with missing or non-informative alt text."""

    if not isinstance(text, str):
        raise ValidationError(f"text must be str, got {type(text).__name__}")

    lines = text.splitlines()
    findings: list[Finding] = []
    in_fence = False

    for line_no, raw_line in enumerate(lines, start=1):
        if _FENCE_RE.match(raw_line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        for m in _IMAGE_RE.finditer(raw_line):
            alt = m.group("alt")
            url = m.group("url")
            col = m.start() + 1
            stripped = alt.strip()

            if stripped == "":
                findings.append(
                    Finding(
                        kind="empty_alt",
                        line=line_no,
                        column=col,
                        raw=alt,
                        detail=f"url={url!r}",
                    )
                )
                continue

            lower = stripped.lower()
            if lower in _PLACEHOLDERS:
                findings.append(
                    Finding(
                        kind="placeholder_alt",
                        line=line_no,
                        column=col,
                        raw=alt,
                        detail=f"placeholder={lower!r}; url={url!r}",
                    )
                )
                continue

            base = _basename(url).lower()
            if base and lower == base:
                findings.append(
                    Finding(
                        kind="filename_as_alt",
                        line=line_no,
                        column=col,
                        raw=alt,
                        detail=f"alt equals url basename={base!r}",
                    )
                )
                continue

            if _FILENAME_RE.match(stripped):
                findings.append(
                    Finding(
                        kind="filename_as_alt",
                        line=line_no,
                        column=col,
                        raw=alt,
                        detail=f"alt looks like a bare filename; url={url!r}",
                    )
                )
                continue

    findings.sort(key=lambda f: (f.line, f.column, f.kind))
    return findings


def format_report(findings: List[Finding]) -> str:
    """Render a deterministic plain-text report. Empty findings → OK line."""

    if not findings:
        return "OK: every image has informative alt text."
    out = [f"FOUND {len(findings)} image-alt finding(s):"]
    for f in findings:
        out.append(
            f"  [{f.kind}] line={f.line} col={f.column} raw={f.raw!r} :: {f.detail}"
        )
    return "\n".join(out)
