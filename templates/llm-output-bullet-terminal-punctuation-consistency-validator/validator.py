r"""Bullet-item terminal-punctuation consistency validator.

Pure stdlib, no I/O. Detects inconsistent terminal punctuation across
the bullet items of a single Markdown-style list. Catches the bug
class where the model writes:

    - first item.
    - second item
    - third item;
    - fourth item.

Each individual line is fine; the *list* is not.

Five finding kinds:

  - mixed_terminator           items in the same list use different
                               terminators (period, semicolon, none, …)
  - trailing_whitespace        item text ends with whitespace before
                               the terminator (or before EOL)
  - empty_item                 item text is empty after stripping
                               markers + whitespace
  - sentence_in_fragment_list  most items are short fragments (no
                               internal sentence-ending punctuation)
                               but at least one item contains a
                               sentence-end midway, suggesting the
                               model glued a paragraph into a bullet
  - inconsistent_capitalization first character of items mixes
                               upper- and lower-case across the list

A "list" is a contiguous run of lines whose first non-whitespace
character matches one of the bullet markers `-`, `*`, `+`, or a
numeric `\d+\.` / `\d+\)` prefix, all sharing the same indent depth.
Blank line or dedent ends the list. Nested sublists are scanned as
their own lists.

Public API:

    validate_bullets(text: str) -> list[Finding]
    format_report(findings: list[Finding]) -> str

Findings sorted by (offset, kind, raw).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


_BULLET_RE = re.compile(
    r"^(?P<indent>[ \t]*)"
    r"(?P<marker>[-*+]|\d+[.)])"
    r"[ \t]+"
    r"(?P<body>.*)$"
)

# Sentence-ending punctuation followed by space + capital letter,
# anywhere except the very end of the body. Signals the body
# contains more than one sentence.
_INTERNAL_SENTENCE_END_RE = re.compile(r"[.!?]\s+[A-Z]")

_TERMINATORS = {
    ".": "period",
    ";": "semicolon",
    ",": "comma",
    ":": "colon",
    "!": "exclamation",
    "?": "question",
}


class ValidationError(TypeError):
    pass


@dataclass(frozen=True)
class Finding:
    kind: str
    offset: int
    raw: str
    detail: str


@dataclass(frozen=True)
class _Item:
    offset: int     # absolute offset of first char of body in text
    indent: str
    marker: str
    body: str       # raw body, no leading/trailing newline
    line: str       # full line text, no trailing newline


def _terminator_of(body: str) -> str:
    s = body.rstrip(" \t")
    if not s:
        return "empty"
    last = s[-1]
    return _TERMINATORS.get(last, "none")


def _has_trailing_ws(body: str) -> bool:
    return body != body.rstrip(" \t")


def _iter_lists(text: str):
    """Yield list-groups: list[ _Item ] sharing one (indent, marker_class)."""
    lines = text.split("\n")
    pos = 0  # cumulative offset
    line_offsets = []
    for line in lines:
        line_offsets.append(pos)
        pos += len(line) + 1

    current: list[_Item] = []
    current_key: tuple[str, str] | None = None  # (indent, marker_class)

    def flush():
        if current:
            yield_buf.append(list(current))
            current.clear()

    yield_buf: list[list[_Item]] = []

    for idx, line in enumerate(lines):
        m = _BULLET_RE.match(line)
        if not m:
            flush()
            current_key = None
            continue
        indent = m.group("indent")
        marker = m.group("marker")
        body = m.group("body")
        marker_class = "num" if marker[0].isdigit() else marker
        key = (indent, marker_class)
        # body offset within full text:
        # = line offset + len(indent) + len(marker) + 1 (single sep char
        #   counted; close enough for reporting — we only use it for
        #   stable sort + caller grep, not for slicing).
        body_off = (
            line_offsets[idx]
            + len(indent)
            + len(marker)
            + 1
        )
        item = _Item(
            offset=body_off,
            indent=indent,
            marker=marker,
            body=body,
            line=line,
        )
        if current_key is None:
            current_key = key
            current.append(item)
        elif key == current_key:
            current.append(item)
        else:
            flush()
            current_key = key
            current.append(item)
    flush()
    for group in yield_buf:
        yield group


def _capclass(ch: str) -> str:
    if ch.isalpha():
        return "upper" if ch.isupper() else "lower"
    return "non-alpha"


def validate_bullets(text: str) -> list[Finding]:
    if not isinstance(text, str):
        raise ValidationError(f"text must be str, got {type(text).__name__}")
    findings: list[Finding] = []

    for group in _iter_lists(text):
        if len(group) < 2:
            # Single-item list: nothing to compare against.
            # Still report empty_item / trailing_whitespace per item.
            for it in group:
                if not it.body.strip():
                    findings.append(
                        Finding(
                            kind="empty_item",
                            offset=it.offset,
                            raw=it.line,
                            detail="item body is empty after stripping",
                        )
                    )
                if _has_trailing_ws(it.body):
                    findings.append(
                        Finding(
                            kind="trailing_whitespace",
                            offset=it.offset,
                            raw=it.line,
                            detail="item body ends with whitespace",
                        )
                    )
            continue

        # Per-item lints first.
        for it in group:
            if not it.body.strip():
                findings.append(
                    Finding(
                        kind="empty_item",
                        offset=it.offset,
                        raw=it.line,
                        detail="item body is empty after stripping",
                    )
                )
            if _has_trailing_ws(it.body):
                findings.append(
                    Finding(
                        kind="trailing_whitespace",
                        offset=it.offset,
                        raw=it.line,
                        detail="item body ends with whitespace",
                    )
                )

        # Terminator consistency.
        terms = [_terminator_of(it.body) for it in group]
        non_empty = [(it, t) for it, t in zip(group, terms) if t != "empty"]
        if non_empty:
            counts: dict[str, int] = {}
            for _, t in non_empty:
                counts[t] = counts.get(t, 0) + 1
            if len(counts) >= 2:
                # majority is the highest count; report all minority items.
                majority = max(counts, key=lambda k: counts[k])
                for it, t in non_empty:
                    if t != majority:
                        findings.append(
                            Finding(
                                kind="mixed_terminator",
                                offset=it.offset,
                                raw=it.line,
                                detail=(
                                    f"terminator={t}; counts={counts}; "
                                    f"majority={majority}"
                                ),
                            )
                        )

        # Sentence-in-fragment-list.
        bodies = [it.body.rstrip(" \t") for it in group]
        # Strip trailing terminator for the "fragment" judgement.
        def _strip_term(s: str) -> str:
            return s[:-1] if s and s[-1] in _TERMINATORS else s
        fragments = [_strip_term(b) for b in bodies]
        # an item is a "sentence-glob" if its body (incl. internal
        # punctuation) contains an internal sentence end.
        is_glob = [
            bool(_INTERNAL_SENTENCE_END_RE.search(b)) for b in bodies
        ]
        if any(is_glob) and not all(is_glob):
            for it, glob in zip(group, is_glob):
                if glob:
                    findings.append(
                        Finding(
                            kind="sentence_in_fragment_list",
                            offset=it.offset,
                            raw=it.line,
                            detail=(
                                "item contains an internal sentence end; "
                                "sibling items are short fragments"
                            ),
                        )
                    )

        # Capitalization consistency on first body char.
        firsts = []
        for it, frag in zip(group, fragments):
            stripped = frag.lstrip()
            if not stripped:
                continue
            firsts.append((it, stripped[0]))
        if firsts:
            classes = [_capclass(ch) for _, ch in firsts]
            cap_counts = {c: classes.count(c) for c in sorted(set(classes))}
            alpha_classes = {
                c: n for c, n in cap_counts.items() if c != "non-alpha"
            }
            if len(alpha_classes) >= 2:
                majority = max(alpha_classes, key=lambda k: alpha_classes[k])
                for (it, ch), klass in zip(firsts, classes):
                    if klass in alpha_classes and klass != majority:
                        findings.append(
                            Finding(
                                kind="inconsistent_capitalization",
                                offset=it.offset,
                                raw=it.line,
                                detail=(
                                    f"first_char={ch!r} class={klass}; "
                                    f"counts={alpha_classes}; "
                                    f"majority={majority}"
                                ),
                            )
                        )

    findings.sort(key=lambda f: (f.offset, f.kind, f.raw))
    return findings


def format_report(findings: list[Finding]) -> str:
    if not findings:
        return "OK: bullet terminal punctuation is consistent.\n"
    lines = [f"FOUND {len(findings)} bullet finding(s):"]
    for f in findings:
        lines.append(
            f"  [{f.kind}] offset={f.offset} :: {f.detail}\n"
            f"    line={f.raw!r}"
        )
    return "\n".join(lines) + "\n"
