"""Pure-stdlib detector for duplicate markdown link reference definitions.

CommonMark allows you to declare a link reference once::

    [docs]: https://example.invalid/docs

and then reuse it inline as ``[docs][]`` or ``[see the docs][docs]``.
The label is **case-insensitively unique**: if the same label is defined
twice, CommonMark says the *first* definition wins and silently drops
the second. Most renderers follow that rule, but some (older
markdown.pl, certain static-site generators) take the *last* one. The
LLM failure mode is identical either way:

- The model produces a long article with a footer block of references.
- It regenerates a paragraph mid-document and emits a new
  ``[api]: https://example.invalid/api/v2`` while the original
  ``[api]: https://example.invalid/api/v1`` is still in the footer.
- Now the same label points at two different URLs and the rendered
  document silently picks one — usually not the one the author wanted.

This detector flags **every duplicate after the first occurrence** of a
given label (compared with CommonMark's case-folded normalization:
lowercase, internal whitespace runs collapsed to a single space,
trimmed). It does *not* flag the first definition. It does not check
that the URL differs — duplicates with identical URLs are still
duplicates and still a smell.

Three finding kinds:

- ``duplicate_label`` — the label was already defined earlier in the
  document (different or identical URL).
- ``duplicate_label_conflicting_url`` — same label, *different* URL
  from the first definition. This is the dangerous one: silent
  divergence depending on renderer.
- ``duplicate_label_conflicting_title`` — same label and URL, but the
  optional title (``"..."``, ``'...'``, ``(...)`` after the URL)
  differs. Hover-text drift.

The detector is **fence-aware**: link reference definitions inside
fenced code blocks (``` ``` ``` and ``~~~``) are ignored. Indented
code blocks (4-space lead on a blank-line-separated block) are also
ignored heuristically.

Out of scope:

- Inline links ``[text](url)``. Those have no labels and cannot
  collide.
- Footnote definitions ``[^id]: ...``. Caught by the footnote-orphan
  detector elsewhere in the family.
- Reference *uses* with no matching definition. Caught by
  ``reference-link-undefined-label-detector``.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Iterable


# CommonMark reference definition shape:
#   [label]: <url-or-bare> "optional title"
# The URL may be in <angle brackets> or bare. Title may use ", ', or ().
_REF_DEF_RE = re.compile(
    r"""
    ^[ ]{0,3}                       # up to 3 leading spaces, never a tab
    \[(?P<label>(?:[^\[\]\\]|\\.)+)\]   # [label] (no nested brackets)
    :[ \t]*                         # colon then optional whitespace
    (?:
        <(?P<url_angle>[^<>\n]*)>   # <url>
        |
        (?P<url_bare>\S+)           # bare url (no whitespace)
    )
    (?:[ \t]+
        (?P<title>
            "(?:[^"\\]|\\.)*"
          | '(?:[^'\\]|\\.)*'
          | \((?:[^()\\]|\\.)*\)
        )
    )?
    [ \t]*$
    """,
    re.VERBOSE,
)

_FENCE_RE = re.compile(r"^(?P<indent>[ ]{0,3})(?P<fence>`{3,}|~{3,})")


@dataclass(frozen=True)
class Finding:
    kind: str
    line: int          # 1-indexed
    label: str         # original label as written
    normalized: str    # CommonMark-folded form
    url: str
    title: str
    first_line: int    # where the winning definition lives
    first_url: str
    first_title: str
    note: str

    def format(self) -> str:
        return (
            f"  [{self.kind}] line={self.line} label={self.label!r} "
            f"first_line={self.first_line} :: {self.note}"
        )


def _normalize_label(label: str) -> str:
    """CommonMark label normalization: case-fold, collapse whitespace, trim."""
    return re.sub(r"\s+", " ", label.strip()).casefold()


def _strip_title_quotes(title: str) -> str:
    if not title:
        return ""
    if len(title) >= 2 and title[0] in "\"'(" and title[-1] in "\"')":
        return title[1:-1]
    return title


def detect_duplicate_reference_definitions(text: str) -> list[Finding]:
    """Return findings for every duplicate reference definition.

    The first occurrence of each (normalized) label is silent; every
    subsequent definition produces one finding.
    """
    findings: list[Finding] = []
    # normalized-label -> (line, raw_label, url, title)
    first_seen: dict[str, tuple[int, str, str, str]] = {}

    in_fence = False
    fence_marker = ""
    fence_indent = 0

    for line_num, raw_line in enumerate(text.splitlines(), start=1):
        # Track fenced code blocks.
        m_fence = _FENCE_RE.match(raw_line)
        if m_fence:
            marker = m_fence.group("fence")
            indent = len(m_fence.group("indent"))
            if not in_fence:
                in_fence = True
                fence_marker = marker[0]
                fence_indent = indent
                continue
            # Closing fence: same char family, length >= opener,
            # indent within 3 of opener.
            if marker[0] == fence_marker and abs(indent - fence_indent) <= 3:
                in_fence = False
                fence_marker = ""
                fence_indent = 0
                continue

        if in_fence:
            continue

        # Heuristic: skip indented code blocks (lines starting with
        # 4+ spaces or a tab). Reference defs allow at most 3 leading
        # spaces, so this is a safe filter.
        if raw_line.startswith("    ") or raw_line.startswith("\t"):
            continue

        m = _REF_DEF_RE.match(raw_line)
        if not m:
            continue

        label = m.group("label")
        normalized = _normalize_label(label)
        url = m.group("url_angle") if m.group("url_angle") is not None else m.group("url_bare")
        title_raw = m.group("title") or ""
        title = _strip_title_quotes(title_raw)

        prior = first_seen.get(normalized)
        if prior is None:
            first_seen[normalized] = (line_num, label, url, title)
            continue

        first_line, _first_label, first_url, first_title = prior

        if url != first_url:
            kind = "duplicate_label_conflicting_url"
            note = f"url={url!r} differs from first url={first_url!r}"
        elif title != first_title:
            kind = "duplicate_label_conflicting_title"
            note = f"title={title!r} differs from first title={first_title!r}"
        else:
            kind = "duplicate_label"
            note = "identical URL and title; redundant definition"

        findings.append(
            Finding(
                kind=kind,
                line=line_num,
                label=label,
                normalized=normalized,
                url=url,
                title=title,
                first_line=first_line,
                first_url=first_url,
                first_title=first_title,
                note=note,
            )
        )

    return findings


def format_report(findings: Iterable[Finding]) -> str:
    findings = list(findings)
    if not findings:
        return "OK: no duplicate link reference definitions found."
    lines = [f"FOUND {len(findings)} duplicate-reference-definition finding(s):"]
    lines.extend(f.format() for f in findings)
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        text = sys.stdin.read()
    else:
        with open(argv[1], "r", encoding="utf-8") as f:
            text = f.read()
    findings = detect_duplicate_reference_definitions(text)
    print(format_report(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
