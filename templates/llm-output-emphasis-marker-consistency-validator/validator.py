r"""Emphasis-marker consistency validator for LLM Markdown output.

Pure stdlib, no I/O. Scans an LLM-generated Markdown blob and reports
the failure mode where the model mixes `*` and `_` markers for the
SAME semantic role inside a single document — e.g. one paragraph uses
`*italic*` and a later paragraph uses `_italic_`, or one bold span is
`**bold**` and another is `__bold__`. Both render identically in most
viewers, so the bug is invisible at preview time. It surfaces when:

  - the doc is fed into a renderer that honors only one style (some
    older Pandoc front-ends, several wiki engines),
  - a downstream linter (`markdownlint` MD049 / MD050, Prettier with
    `--prose-wrap`) flips half the document on autoformat and the
    diff explodes,
  - a RAG chunker keyed on string-equality fingerprints of inline
    spans treats `*x*` and `_x_` as different snippets even though
    they render the same.

Five finding kinds, sorted by `(offset, kind)` for byte-identical
re-runs:

  - mixed_italic_marker     the document contains BOTH `*x*`
                            (asterisk italic) AND `_x_` (underscore
                            italic) spans. Reported once per minority
                            span (so a 7-asterisk / 2-underscore
                            document fires twice — on the two
                            underscore spans — with the explicit
                            count table and the majority style so a
                            repair prompt is one string interpolation
                            away).
  - mixed_bold_marker       same but for bold (`**x**` vs `__x__`).
                            Tracked separately from italic because a
                            doc may legitimately be consistent on
                            italic and inconsistent on bold (or vice
                            versa) and a single mixed-marker
                            verdict would hide the partial-fix
                            opportunity.
  - bold_in_italic_style    a span uses `***x***` (asterisk
                            bold-italic) AND another uses `___x___`
                            (underscore bold-italic). Distinct
                            because some renderers interpret triple
                            markers differently from doubles.
  - unbalanced_marker       a line contains an ODD number of
                            standalone `*` or `_` markers (after
                            removing escaped `\*` and `\_`, after
                            skipping fenced code, after skipping
                            inline code spans), strongly indicating
                            an unclosed emphasis span. Reported per
                            line because the column-of-first-stray
                            is the actionable fix.
  - intraword_underscore    `_` used INSIDE a word (e.g. `snake_case`
                            in prose, NOT in a code span). CommonMark
                            does not treat intraword underscores as
                            emphasis, but several renderers
                            (Discount, older Markdown.pl,
                            Slack-flavor) DO, so a `snake_case`
                            identifier in the prose body silently
                            italicizes the middle. The fix is
                            backticks; reported so the author can
                            wrap the identifier in `` ` ``.

Fenced code blocks (` ``` ` or `~~~`) are SKIPPED entirely. Inline
code spans (`` `...` ``) are stripped from each line before scanning
so an asterisk inside `` `a*b` `` is not counted. Backslash-escaped
markers (`\*`, `\_`) are removed before counting.

Public API:

    detect_emphasis_inconsistency(text: str) -> list[Finding]
    format_report(findings: list[Finding]) -> str

Pure function; no Markdown parser, no language detection, no
networking. One forward pass over the lines tracking fence state.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


class ValidationError(ValueError):
    """Raised when input is not a `str`."""


@dataclass(frozen=True)
class Finding:
    kind: str
    line_number: int  # 1-based
    column: int       # 1-based
    offset: int       # 0-based byte offset in original text
    raw: str          # the full line (without trailing newline)
    detail: str


_FENCE_RE = re.compile(r"^[ \t]*(```|~~~)")

# Inline code spans `...` (single-backtick, non-greedy, no embedded `)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")

# Bold-italic asterisk: `***word***`
_TRIPLE_AST_RE = re.compile(r"(?<!\*)\*\*\*([^*\s][^*\n]*?[^*\s]|[^*\s])\*\*\*(?!\*)")
# Bold-italic underscore: `___word___`
_TRIPLE_UND_RE = re.compile(r"(?<!_)___([^_\s][^_\n]*?[^_\s]|[^_\s])___(?!_)")

# Bold asterisk: `**word**` (not part of `***`)
_BOLD_AST_RE = re.compile(r"(?<!\*)\*\*([^*\s][^*\n]*?[^*\s]|[^*\s])\*\*(?!\*)")
# Bold underscore: `__word__`
_BOLD_UND_RE = re.compile(r"(?<!_)__([^_\s][^_\n]*?[^_\s]|[^_\s])__(?!_)")

# Italic asterisk: `*word*` (not `**`, `***`)
_ITALIC_AST_RE = re.compile(r"(?<!\*)\*(?!\*)([^*\s][^*\n]*?[^*\s]|[^*\s])(?<!\*)\*(?!\*)")
# Italic underscore: `_word_` (not `__`, `___`), and word-boundary aware
# (intraword underscores like snake_case do not count as italic per
# CommonMark, but we DETECT them separately below).
_ITALIC_UND_RE = re.compile(r"(?<![\w_])_(?!_)([^_\s][^_\n]*?[^_\s]|[^_\s])_(?!_)(?!\w)")

# Intraword underscore in prose: `\w_\w` (after code is stripped). We
# require at least one alnum on EACH side of the underscore to flag.
_INTRAWORD_UND_RE = re.compile(r"\w_\w")


def _strip_inline_code(line: str) -> str:
    """Replace each `...` span with same-length spaces so column math
    in the original line still works against indices in the stripped
    line."""
    out_parts: list[str] = []
    last = 0
    for m in _INLINE_CODE_RE.finditer(line):
        out_parts.append(line[last:m.start()])
        out_parts.append(" " * (m.end() - m.start()))
        last = m.end()
    out_parts.append(line[last:])
    return "".join(out_parts)


def _strip_escapes(line: str) -> str:
    r"""Replace ``\*`` and ``\_`` with two spaces (preserve column math)."""
    return line.replace(r"\*", "  ").replace(r"\_", "  ")


def _count_unbalanced(line: str) -> tuple[int, int]:
    """Return (col_of_first_unbalanced_or_-1, char_kind_marker_count).
    We count standalone `*` and `_` markers (after stripping triples,
    doubles, then singles) — but a simpler signal that catches the
    common bug is: count `*` and `_` chars in the cleaned line and
    flag if either parity is odd. The returned column is the byte
    position (1-based) of the first `*` or `_` in the line (or -1)."""
    # We treat the cleaned line as our domain.
    star_count = line.count("*")
    und_count = line.count("_")
    # Caller decides which kind is unbalanced based on parity.
    star_col = line.find("*") + 1 if star_count else -1
    und_col = line.find("_") + 1 if und_count else -1
    return (star_count, und_count) + (star_col, und_col) if False else (star_count, und_count)  # noqa


def detect_emphasis_inconsistency(text: str) -> list[Finding]:
    if not isinstance(text, str):
        raise ValidationError(
            f"text must be str, got {type(text).__name__}"
        )

    findings: list[Finding] = []
    in_fence = False
    fence_char: str | None = None
    lines = text.split("\n")
    if text.endswith("\n") and lines and lines[-1] == "":
        lines = lines[:-1]

    # First pass: collect per-span info to decide majority styles.
    italic_ast_spans: list[tuple[int, int, int, str]] = []  # (line, col, off, raw)
    italic_und_spans: list[tuple[int, int, int, str]] = []
    bold_ast_spans: list[tuple[int, int, int, str]] = []
    bold_und_spans: list[tuple[int, int, int, str]] = []
    bolditalic_ast_spans: list[tuple[int, int, int, str]] = []
    bolditalic_und_spans: list[tuple[int, int, int, str]] = []

    # Track running byte offsets so per-span `offset` is in the
    # ORIGINAL text (jump-to-byte from the report works).
    line_starts: list[int] = []
    cursor = 0
    for raw in lines:
        line_starts.append(cursor)
        cursor += len(raw) + 1  # +1 for the "\n" we split on

    for idx, raw in enumerate(lines, start=1):
        stripped_lead = raw.lstrip()
        m_fence = _FENCE_RE.match(raw)
        if m_fence:
            fc = m_fence.group(1)
            if not in_fence:
                in_fence = True
                fence_char = fc
            elif fence_char == fc:
                in_fence = False
                fence_char = None
            continue
        if in_fence:
            continue

        # Strip inline code (preserve column indices) then escapes.
        cleaned = _strip_escapes(_strip_inline_code(raw))

        # Collect spans. We strip triples first by replacing them with
        # spaces so doubles/singles regexes don't double-fire on them.
        work = cleaned
        for m in _TRIPLE_AST_RE.finditer(work):
            bolditalic_ast_spans.append(
                (idx, m.start() + 1, line_starts[idx - 1] + m.start(), raw)
            )
        for m in _TRIPLE_UND_RE.finditer(work):
            bolditalic_und_spans.append(
                (idx, m.start() + 1, line_starts[idx - 1] + m.start(), raw)
            )
        # Mask triples so doubles don't re-match the inner `**...**`.
        work = _TRIPLE_AST_RE.sub(lambda m: " " * (m.end() - m.start()), work)
        work = _TRIPLE_UND_RE.sub(lambda m: " " * (m.end() - m.start()), work)

        for m in _BOLD_AST_RE.finditer(work):
            bold_ast_spans.append(
                (idx, m.start() + 1, line_starts[idx - 1] + m.start(), raw)
            )
        for m in _BOLD_UND_RE.finditer(work):
            bold_und_spans.append(
                (idx, m.start() + 1, line_starts[idx - 1] + m.start(), raw)
            )
        # Mask doubles so singles don't re-fire on inner chars.
        work = _BOLD_AST_RE.sub(lambda m: " " * (m.end() - m.start()), work)
        work = _BOLD_UND_RE.sub(lambda m: " " * (m.end() - m.start()), work)

        for m in _ITALIC_AST_RE.finditer(work):
            italic_ast_spans.append(
                (idx, m.start() + 1, line_starts[idx - 1] + m.start(), raw)
            )
        for m in _ITALIC_UND_RE.finditer(work):
            italic_und_spans.append(
                (idx, m.start() + 1, line_starts[idx - 1] + m.start(), raw)
            )
        # Mask matched singles too so intraword check below sees only
        # the truly stray underscores.
        work = _ITALIC_AST_RE.sub(lambda m: " " * (m.end() - m.start()), work)
        work = _ITALIC_UND_RE.sub(lambda m: " " * (m.end() - m.start()), work)

        # Intraword underscore detection on the post-masked `work`
        # line — masking has replaced matched bold/bolditalic/italic
        # underscore markers with spaces, so we won't false-positive
        # on the underscores INSIDE valid `__bold__` / `___bi___` /
        # `_italic_` spans. The remaining underscores are either
        # truly stray (caught below by `unbalanced_marker` if odd)
        # or genuinely intraword (`snake_case` in prose).
        for m in _INTRAWORD_UND_RE.finditer(work):
            findings.append(Finding(
                kind="intraword_underscore",
                line_number=idx,
                column=m.start() + 2,  # the underscore itself
                offset=line_starts[idx - 1] + m.start() + 1,
                raw=raw,
                detail=(
                    f"intraword underscore at byte {m.start() + 2}: "
                    f"{cleaned[m.start():m.end()]!r} — wrap identifier "
                    "in backticks to avoid Slack-flavor italic"
                ),
            ))

        # Unbalanced markers on this line. Count `*` and `_` in the
        # cleaned (escapes-removed, code-stripped) line.
        star_count = cleaned.count("*")
        und_count = cleaned.count("_")
        if star_count % 2 == 1:
            col = cleaned.find("*") + 1
            findings.append(Finding(
                kind="unbalanced_marker",
                line_number=idx,
                column=col,
                offset=line_starts[idx - 1] + col - 1,
                raw=raw,
                detail=(
                    f"odd number of '*' markers on line ({star_count}) — "
                    "unclosed emphasis span"
                ),
            ))
        if und_count % 2 == 1:
            col = cleaned.find("_") + 1
            findings.append(Finding(
                kind="unbalanced_marker",
                line_number=idx,
                column=col,
                offset=line_starts[idx - 1] + col - 1,
                raw=raw,
                detail=(
                    f"odd number of '_' markers on line ({und_count}) — "
                    "unclosed emphasis span"
                ),
            ))

    # Cross-document consistency: italic
    if italic_ast_spans and italic_und_spans:
        n_ast = len(italic_ast_spans)
        n_und = len(italic_und_spans)
        if n_ast >= n_und:
            majority = "asterisk"
            minority_spans = italic_und_spans
            minority_marker = "_"
        else:
            majority = "underscore"
            minority_spans = italic_ast_spans
            minority_marker = "*"
        for (line, col, off, raw) in minority_spans:
            findings.append(Finding(
                kind="mixed_italic_marker",
                line_number=line,
                column=col,
                offset=off,
                raw=raw,
                detail=(
                    f"italic uses '{minority_marker}' but document "
                    f"majority is {majority} (counts: asterisk={n_ast}, "
                    f"underscore={n_und})"
                ),
            ))

    # Cross-document consistency: bold
    if bold_ast_spans and bold_und_spans:
        n_ast = len(bold_ast_spans)
        n_und = len(bold_und_spans)
        if n_ast >= n_und:
            majority = "asterisk"
            minority_spans = bold_und_spans
            minority_marker = "__"
        else:
            majority = "underscore"
            minority_spans = bold_ast_spans
            minority_marker = "**"
        for (line, col, off, raw) in minority_spans:
            findings.append(Finding(
                kind="mixed_bold_marker",
                line_number=line,
                column=col,
                offset=off,
                raw=raw,
                detail=(
                    f"bold uses '{minority_marker}' but document "
                    f"majority is {majority} (counts: asterisk={n_ast}, "
                    f"underscore={n_und})"
                ),
            ))

    # Cross-document consistency: bold-italic (triples)
    if bolditalic_ast_spans and bolditalic_und_spans:
        n_ast = len(bolditalic_ast_spans)
        n_und = len(bolditalic_und_spans)
        if n_ast >= n_und:
            majority = "asterisk"
            minority_spans = bolditalic_und_spans
            minority_marker = "___"
        else:
            majority = "underscore"
            minority_spans = bolditalic_ast_spans
            minority_marker = "***"
        for (line, col, off, raw) in minority_spans:
            findings.append(Finding(
                kind="bold_in_italic_style",
                line_number=line,
                column=col,
                offset=off,
                raw=raw,
                detail=(
                    f"bold-italic uses '{minority_marker}' but document "
                    f"majority is {majority} (counts: asterisk={n_ast}, "
                    f"underscore={n_und})"
                ),
            ))

    findings.sort(key=lambda f: (f.offset, f.kind))
    return findings


def format_report(findings: list[Finding]) -> str:
    if not findings:
        return "OK: emphasis markers consistent.\n"
    out = [f"FOUND {len(findings)} emphasis finding(s):"]
    for f in findings:
        out.append(
            f"  [{f.kind}] line={f.line_number} col={f.column} "
            f"off={f.offset} :: {f.detail}"
        )
        out.append(f"    line={f.raw!r}")
    out.append("")
    return "\n".join(out)


__all__ = [
    "Finding",
    "ValidationError",
    "detect_emphasis_inconsistency",
    "format_report",
]
