r"""Emoji density detector for LLM Markdown / prose output.

Pure stdlib, no I/O. Scans an LLM output blob and reports two
finding kinds plus a document-level density verdict:

  - per_line_dense    a single line carries more emoji than the
                      configured per-line cap; the line itself is
                      noisy regardless of the document average
  - cluster           >=2 emoji appear back-to-back (allowing for
                      a single ASCII space or ZWJ between them);
                      back-to-back emoji are the strongest visual
                      tell of a "cheerful assistant" register and
                      almost never appear in human-written prose
                      outside of social-media bios

  - density_over_cap  document-level: total emoji per 100 grapheme-
                      ish "words" exceeds the configured cap;
                      reported once at line=0 with col=0

Why "emoji"? Detected as Unicode codepoints in the standard emoji
ranges (BMP symbols block, supplemental symbols & pictographs,
miscellaneous symbols, dingbats, transport & map, regional
indicators, plus variation selector U+FE0F handling and ZWJ
U+200D handling so a multi-codepoint emoji like a family glyph
counts as ONE emoji, not five). The detector deliberately does
NOT consult a fully-up-to-date emoji table — it uses block ranges
that have been stable since Unicode 6.0 and have not had a
non-emoji codepoint added since. False positives are ASCII
characters U+0000..U+007F (never matched) and CJK glyphs (never
matched). False negatives are post-2024 emoji additions that
land outside these blocks; in practice no model-produced output
has ever needed a 2024+ emoji to be flagged because the issue is
density, not coverage.

Public API:

    detect_emoji_issues(
        text: str,
        *,
        per_line_cap: int = 3,
        per_100_words_cap: float = 5.0,
    ) -> list[Finding]
    format_report(findings: list[Finding]) -> str

Findings are sorted by (line_number, kind, column).

Why this exists: an LLM-drafted commit message, PR description, or
status report that lands in `git log` / `gh pr view` / a wiki
permanently tags the document as "AI-generated" the moment a
reader sees three sparkles in a row. Editors do not strip emoji.
A pre-publish gate that flags `cluster` findings catches the
single most legible "AI tell" in <1ms per kilobyte.
"""

from __future__ import annotations

from dataclasses import dataclass


class ValidationError(ValueError):
    """Raised on bad input."""


@dataclass(frozen=True)
class Finding:
    kind: str
    line_number: int  # 1-based; 0 for document-level findings
    column: int       # 1-based; 0 for document-level findings
    raw: str
    detail: str


# Codepoint ranges that are entirely emoji / pictographic symbols.
# Each entry is (lo, hi) inclusive. Sourced from the Unicode 6.0+
# emoji blocks that have remained stable.
_EMOJI_RANGES: tuple[tuple[int, int], ...] = (
    (0x1F300, 0x1F5FF),  # Misc symbols & pictographs
    (0x1F600, 0x1F64F),  # Emoticons
    (0x1F680, 0x1F6FF),  # Transport & map
    (0x1F700, 0x1F77F),  # Alchemical
    (0x1F780, 0x1F7FF),  # Geometric shapes ext
    (0x1F800, 0x1F8FF),  # Supplemental arrows-c
    (0x1F900, 0x1F9FF),  # Supplemental symbols & pictographs
    (0x1FA00, 0x1FA6F),  # Chess symbols
    (0x1FA70, 0x1FAFF),  # Symbols & pictographs ext-a
    (0x2600, 0x26FF),    # Misc symbols (sun, cloud, etc.)
    (0x2700, 0x27BF),    # Dingbats (sparkles, check, cross, etc.)
    (0x1F1E6, 0x1F1FF),  # Regional indicators (flags)
)

_VARIATION_SELECTOR_16 = 0x0FE0F  # U+FE0F (emoji presentation)
_ZWJ = 0x200D                     # U+200D (zero-width joiner)


def _is_emoji_cp(cp: int) -> bool:
    for lo, hi in _EMOJI_RANGES:
        if lo <= cp <= hi:
            return True
    return False


def _scan_emoji_clusters(line: str) -> list[tuple[int, str]]:
    """Return list of (column_1based, cluster_text) for each emoji
    cluster on this line. A cluster groups codepoints joined by ZWJ
    or followed by U+FE0F so a multi-codepoint emoji counts as one.
    """
    clusters: list[tuple[int, str]] = []
    i = 0
    n = len(line)
    while i < n:
        cp = ord(line[i])
        if _is_emoji_cp(cp):
            start = i
            i += 1
            # Consume trailing VS16 / ZWJ + emoji extensions.
            while i < n:
                cp2 = ord(line[i])
                if cp2 == _VARIATION_SELECTOR_16:
                    i += 1
                    continue
                if cp2 == _ZWJ and i + 1 < n and _is_emoji_cp(ord(line[i + 1])):
                    i += 2
                    # And consume any VS16 after the joined glyph
                    while i < n and ord(line[i]) == _VARIATION_SELECTOR_16:
                        i += 1
                    continue
                break
            clusters.append((start + 1, line[start:i]))
        else:
            i += 1
    return clusters


def _word_count(text: str) -> int:
    """Cheap whitespace word count, ignoring lines that are only
    fenced-code separators. Used as the denominator for density.
    """
    n = 0
    for tok in text.split():
        # Strip stray emoji from token before counting; an emoji
        # alone is not a word.
        stripped = "".join(c for c in tok if not _is_emoji_cp(ord(c)))
        if stripped:
            n += 1
    return n


def detect_emoji_issues(
    text: str,
    *,
    per_line_cap: int = 3,
    per_100_words_cap: float = 5.0,
) -> list[Finding]:
    if not isinstance(text, str):
        raise ValidationError(f"text must be str, got {type(text).__name__}")
    if per_line_cap < 1:
        raise ValidationError("per_line_cap must be >= 1")
    if per_100_words_cap <= 0:
        raise ValidationError("per_100_words_cap must be > 0")

    findings: list[Finding] = []
    total_emoji = 0
    lines = text.split("\n")
    if text.endswith("\n") and lines and lines[-1] == "":
        lines = lines[:-1]

    for idx, raw in enumerate(lines, start=1):
        clusters = _scan_emoji_clusters(raw)
        total_emoji += len(clusters)

        if len(clusters) > per_line_cap:
            findings.append(Finding(
                kind="per_line_dense",
                line_number=idx,
                column=clusters[0][0],
                raw=raw,
                detail=(
                    f"{len(clusters)} emoji on this line "
                    f"(cap={per_line_cap})"
                ),
            ))

        # Cluster: two emoji whose separation is 0 or 1 ASCII space.
        # We already merged ZWJ-joined codepoints into one cluster,
        # so this catches "🎉🚀" and "🎉 🚀" but not "🎉, and 🚀".
        for a, b in zip(clusters, clusters[1:]):
            a_col, a_text = a
            b_col, _ = b
            gap_start = a_col - 1 + len(a_text)
            gap = raw[gap_start:b_col - 1]
            if gap == "" or gap == " ":
                findings.append(Finding(
                    kind="cluster",
                    line_number=idx,
                    column=a_col,
                    raw=raw,
                    detail=(
                        f"adjacent emoji at columns {a_col} and {b_col} "
                        f"(gap={gap!r})"
                    ),
                ))

    words = _word_count(text)
    if words > 0:
        density = (total_emoji / words) * 100.0
        if density > per_100_words_cap:
            findings.append(Finding(
                kind="density_over_cap",
                line_number=0,
                column=0,
                raw="",
                detail=(
                    f"document density {density:.2f} emoji per 100 words "
                    f"(cap={per_100_words_cap}, total_emoji={total_emoji}, "
                    f"words={words})"
                ),
            ))

    findings.sort(key=lambda f: (f.line_number, f.kind, f.column))
    return findings


def format_report(findings: list[Finding]) -> str:
    if not findings:
        return "OK: emoji density within caps.\n"
    out = [f"FOUND {len(findings)} emoji finding(s):"]
    for f in findings:
        loc = (
            "doc-level"
            if f.line_number == 0
            else f"line={f.line_number} col={f.column}"
        )
        out.append(f"  [{f.kind}] {loc} :: {f.detail}")
        if f.raw:
            out.append(f"    line={f.raw!r}")
    out.append("")
    return "\n".join(out)


__all__ = [
    "Finding",
    "ValidationError",
    "detect_emoji_issues",
    "format_report",
]
