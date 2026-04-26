"""Pure-stdlib detector for bare URL vs Markdown link inconsistency in LLM output.

LLMs frequently mix three different ways of expressing the same URL within
one document:

    https://example.com/path                 (bare)
    <https://example.com/path>               (autolink)
    [example.com](https://example.com/path)  (markdown link)

All three render in some form, but only the markdown-link form survives a
plain-text export with link text intact, only the autolink form renders as
clickable in strict CommonMark contexts that disable bare-URL detection, and
mixing the three styles in one document signals that the model wasn't given
a style instruction or wasn't asked to honor one.

This detector reports:

    bare_url           A URL not wrapped in <...> and not used as a markdown
                       link target. Reported with the URL, the offset, the
                       line number, and a flag for whether it sits inside a
                       fenced or inline code span.
    autolink           <https://...>-style URL.
    markdown_link      [text](url) form.

It then computes a *style-consistency* verdict over the document:

    consistent          all non-code URLs use the same kind
    mixed_styles        more than one kind appears outside code; the report
                        names the dominant kind and lists the off-style
                        occurrences so a one-shot fix prompt can target them
    no_urls             nothing to evaluate

Code-aware: URLs inside fenced code blocks (``` ... ```) and inline code
spans (`...`) are reported with `in_code=True` and are excluded from the
consistency verdict by default — code samples legitimately need bare URLs
(curl examples, log lines) and shouldn't force the prose around them to
also use bare URLs.

Reference-style markdown links ([text][label] + [label]: url) are NOT
treated as a style violation against inline links; they're a legitimate
fourth form. They are reported as kind="markdown_link" with a `reference`
flag so a strict-style policy can still see them, but they don't fail the
default consistency check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import List, Tuple, Dict, Optional


# A deliberately narrow URL pattern: http/https only, no auth or fragment
# magic. The detector errs toward NOT classifying ambiguous strings as URLs;
# a missed bare URL is a quiet false negative, but a false positive on a
# string like `s3://bucket` would be loud and annoying.
_URL_RE = re.compile(r"https?://[^\s<>()\[\]`'\"]+")
# Trim trailing punctuation that's almost always sentence-level, not URL.
_TRAIL_PUNCT = ".,;:!?)]}"


@dataclass(frozen=True)
class Finding:
    offset: int
    line_no: int           # 1-based
    kind: str              # "bare_url" | "autolink" | "markdown_link"
    url: str
    in_code: bool
    reference: bool        # True only for [text][label]+[label]: url form
    raw: str               # the matched substring as it appears in source


def _line_no_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _build_code_mask(text: str) -> List[bool]:
    """For each character index in `text`, True iff it is inside a fenced
    code block (``` or ~~~) or an inline code span (`...`).
    """
    mask = [False] * len(text)
    i = 0
    n = len(text)
    in_fence = False
    fence_char = ""
    while i < n:
        # Detect fence open / close on a line that begins with ``` or ~~~
        if (i == 0 or text[i - 1] == "\n") and (
            text.startswith("```", i) or text.startswith("~~~", i)
        ):
            ch = text[i]
            if not in_fence:
                in_fence = True
                fence_char = ch
                # Mask the fence line itself
                eol = text.find("\n", i)
                if eol == -1:
                    eol = n
                for j in range(i, eol):
                    mask[j] = True
                i = eol
                continue
            elif fence_char == ch:
                in_fence = False
                eol = text.find("\n", i)
                if eol == -1:
                    eol = n
                for j in range(i, eol):
                    mask[j] = True
                i = eol
                continue
        if in_fence:
            mask[i] = True
            i += 1
            continue
        # Inline code: backtick run of length k, find matching run of same length
        if text[i] == "`":
            k = 0
            while i + k < n and text[i + k] == "`":
                k += 1
            close_seq = "`" * k
            close_idx = text.find(close_seq, i + k)
            if close_idx != -1:
                for j in range(i, close_idx + k):
                    mask[j] = True
                i = close_idx + k
                continue
            # Unmatched: just step past
            i += k
            continue
        i += 1
    return mask


def _strip_trailing_punct(url: str) -> str:
    while url and url[-1] in _TRAIL_PUNCT:
        url = url[:-1]
    return url


def detect_url_styles(text: str) -> List[Finding]:
    """Return all URL occurrences in `text`, classified by kind.

    Findings are sorted by `offset`. Each character of `text` produces at
    most one finding; the precedence is markdown_link → autolink →
    bare_url, so a `[x](https://e.com)` is not also reported as a bare URL.
    """
    if not isinstance(text, str):
        raise TypeError("detect_url_styles expects str")

    code_mask = _build_code_mask(text)
    consumed = [False] * len(text)
    findings: List[Finding] = []

    # Reference link definitions: [label]: url
    refdef_re = re.compile(
        r"^\s*\[([^\]\n]+)\]:\s*(\S+)\s*$", re.MULTILINE,
    )
    ref_labels: Dict[str, str] = {}
    for m in refdef_re.finditer(text):
        label = m.group(1).strip().lower()
        url = m.group(2)
        ref_labels[label] = url
        # Mark the URL portion as consumed so it's not also reported as bare
        url_start = m.start(2)
        for j in range(url_start, m.end(2)):
            consumed[j] = True
        # Record a markdown_link finding for the ref definition itself
        if _URL_RE.match(url):
            in_code = code_mask[url_start] if url_start < len(text) else False
            findings.append(Finding(
                offset=url_start,
                line_no=_line_no_of(text, url_start),
                kind="markdown_link",
                url=url,
                in_code=in_code,
                reference=True,
                raw=m.group(0).strip(),
            ))

    # Inline markdown links: [text](url)
    inline_link_re = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")
    for m in inline_link_re.finditer(text):
        url = m.group(2)
        url_start = m.start(2)
        if not _URL_RE.match(url):
            continue
        for j in range(m.start(), m.end()):
            consumed[j] = True
        in_code = code_mask[url_start] if url_start < len(text) else False
        findings.append(Finding(
            offset=m.start(),
            line_no=_line_no_of(text, m.start()),
            kind="markdown_link",
            url=url,
            in_code=in_code,
            reference=False,
            raw=m.group(0),
        ))

    # Reference-style usages: [text][label] — only when label resolves
    refuse_re = re.compile(r"\[([^\]\n]+)\]\[([^\]\n]*)\]")
    for m in refuse_re.finditer(text):
        label = (m.group(2) or m.group(1)).strip().lower()
        if label in ref_labels:
            url = ref_labels[label]
            for j in range(m.start(), m.end()):
                consumed[j] = True
            in_code = code_mask[m.start()] if m.start() < len(text) else False
            findings.append(Finding(
                offset=m.start(),
                line_no=_line_no_of(text, m.start()),
                kind="markdown_link",
                url=url,
                in_code=in_code,
                reference=True,
                raw=m.group(0),
            ))

    # Autolinks: <https://...>
    autolink_re = re.compile(r"<(https?://[^\s<>]+)>")
    for m in autolink_re.finditer(text):
        if any(consumed[j] for j in range(m.start(), m.end())):
            continue
        url = m.group(1)
        for j in range(m.start(), m.end()):
            consumed[j] = True
        in_code = code_mask[m.start()] if m.start() < len(text) else False
        findings.append(Finding(
            offset=m.start(),
            line_no=_line_no_of(text, m.start()),
            kind="autolink",
            url=url,
            in_code=in_code,
            reference=False,
            raw=m.group(0),
        ))

    # Remaining bare URLs
    for m in _URL_RE.finditer(text):
        if any(consumed[j] for j in range(m.start(), m.end())):
            continue
        url = _strip_trailing_punct(m.group(0))
        in_code = code_mask[m.start()] if m.start() < len(text) else False
        findings.append(Finding(
            offset=m.start(),
            line_no=_line_no_of(text, m.start()),
            kind="bare_url",
            url=url,
            in_code=in_code,
            reference=False,
            raw=m.group(0)[: len(url)],
        ))

    findings.sort(key=lambda f: f.offset)
    return findings


@dataclass(frozen=True)
class ConsistencyVerdict:
    verdict: str                    # "consistent" | "mixed_styles" | "no_urls"
    dominant_kind: Optional[str]    # most common non-code kind
    counts: Dict[str, int]          # kind -> count, non-code only
    off_style: List[Finding]        # findings whose kind != dominant_kind


def evaluate_consistency(
    findings: List[Finding],
    *,
    include_code: bool = False,
    treat_reference_as_inline: bool = True,
) -> ConsistencyVerdict:
    """Return the document-level style verdict.

    By default code findings are excluded (curl examples should be allowed
    to use bare URLs even in a markdown-link-style document). Set
    `include_code=True` for strict-mode pipelines.

    Reference-style markdown links collapse into the markdown_link bucket
    by default; pass `treat_reference_as_inline=False` to count them as
    their own kind.
    """
    pool = [f for f in findings if include_code or not f.in_code]
    if not pool:
        return ConsistencyVerdict(
            verdict="no_urls", dominant_kind=None, counts={}, off_style=[],
        )

    def bucket(f: Finding) -> str:
        if f.kind == "markdown_link" and f.reference and not treat_reference_as_inline:
            return "markdown_reference_link"
        return f.kind

    counts: Dict[str, int] = {}
    for f in pool:
        b = bucket(f)
        counts[b] = counts.get(b, 0) + 1

    if len(counts) == 1:
        only = next(iter(counts))
        return ConsistencyVerdict(
            verdict="consistent",
            dominant_kind=only,
            counts=counts,
            off_style=[],
        )

    # Ties broken by a fixed preference order so the verdict is stable.
    pref = ("markdown_link", "autolink", "bare_url", "markdown_reference_link")
    dominant = max(counts.keys(), key=lambda k: (counts[k], -pref.index(k) if k in pref else 0))
    off_style = [f for f in pool if bucket(f) != dominant]
    return ConsistencyVerdict(
        verdict="mixed_styles",
        dominant_kind=dominant,
        counts=counts,
        off_style=off_style,
    )


def format_report(findings: List[Finding], verdict: ConsistencyVerdict) -> str:
    lines = []
    if not findings:
        lines.append("FINDINGS: none")
    else:
        lines.append(f"FINDINGS ({len(findings)}):")
        for f in findings:
            tag = []
            if f.in_code:
                tag.append("in_code")
            if f.reference:
                tag.append("reference")
            tag_str = (" [" + ",".join(tag) + "]") if tag else ""
            lines.append(
                f"  line {f.line_no} offset {f.offset}: {f.kind} {f.url}{tag_str}"
            )
    lines.append("")
    lines.append(f"VERDICT: {verdict.verdict}")
    if verdict.dominant_kind is not None:
        lines.append(f"  dominant_kind: {verdict.dominant_kind}")
    if verdict.counts:
        kc = ", ".join(f"{k}={v}" for k, v in sorted(verdict.counts.items()))
        lines.append(f"  counts: {kc}")
    if verdict.off_style:
        lines.append(f"  off_style ({len(verdict.off_style)}):")
        for f in verdict.off_style:
            lines.append(f"    line {f.line_no}: {f.kind} {f.url}")
    return "\n".join(lines)


def finding_as_dict(f: Finding) -> dict:
    return asdict(f)
