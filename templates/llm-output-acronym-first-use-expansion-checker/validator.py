"""Acronym first-use expansion checker for LLM output.

Pure stdlib, no I/O. Scans an LLM-generated prose blob and reports
acronyms used WITHOUT a preceding expansion at their FIRST occurrence
in the document — the artifact class where the model writes
"... the SLO was met ..." in the opening paragraph and only later (or
never) defines it as "service-level objective (SLO)".

The bug is invisible at preview time but surfaces when:

  - the doc is read by an audience without the same domain context
    as the model's training distribution (a CFO reading a platform
    incident postmortem; a junior engineer reading a senior's design
    doc),
  - downstream summarization / RAG retrieval keys on the acronym
    string and loses the expansion entirely (the expansion in
    paragraph 7 never makes it into the chunk that contains the
    first reference in paragraph 1),
  - the doc is auto-translated to another language and the
    translator silently passes the acronym through without the
    target-language expansion the reader needs.

Five finding kinds, sorted by `(offset, kind)` for byte-identical
re-runs:

  - undefined_first_use     acronym appears for the first time in
                            the doc with NO expansion in the
                            immediately-preceding context (default:
                            same sentence, before the acronym, with
                            an expansion form of `Long Form (ACR)`
                            or `Long Form (ACR)` style). The detail
                            string carries the acronym and the
                            sentence it appeared in so the repair
                            prompt is one interpolation away.
  - inconsistent_expansion  the acronym is expanded MORE THAN ONCE
                            in the doc with DIFFERENT long forms
                            (e.g. `LLM (large language model)` and
                            later `LLM (language learning module)`).
                            Almost always a model artifact —
                            expansion drift across paragraphs is a
                            strong signal the model lost the binding.
  - redundant_re_expansion  the acronym is expanded AGAIN later in
                            the doc with the SAME long form. Soft
                            warning kind — readers do not need the
                            second `service-level objective (SLO)`
                            once the binding is established. Useful
                            for tightening prompts; demote to
                            `info`-level if your house style allows
                            re-expansion at section boundaries.
  - lowercase_after_acronym a lowercase variant of the acronym
                            (e.g. `slo`) appears after the uppercase
                            form was introduced. Often a model
                            artifact where the model briefly forgets
                            the term is an acronym and writes it as
                            an ordinary noun.
  - never_expanded          acronym appears AT LEAST `min_repeats`
                            times (default 2) in the doc and is
                            NEVER expanded anywhere. Distinct from
                            `undefined_first_use` — the latter fires
                            even on a single use, this fires only
                            when the acronym is repeated and still
                            undefined, raising the severity.

An "acronym candidate" is a token of `≥ min_len` (default 2) ASCII
uppercase letters, optionally followed by a digit suffix (`SLO`,
`HTTP2`, `TLS13`). Pure-digit tokens are excluded. Tokens in a
configurable `allowlist` (default: a small set of universally-known
acronyms — `OK`, `USA`, `URL`, `API`, `JSON`, `HTTP`, `HTTPS`, `CSS`,
`HTML`, `SQL`, `XML`, `YAML`, `CSV`, `PDF`, `RAM`, `CPU`, `GPU`, `OS`,
`UI`, `UX`, `ID`, `PR`, `CI`, `CD`, `IO`, `AM`, `PM`, `UTC`) is
NEVER flagged — they are universal in software-engineering prose and
expanding them wastes the reader's time.

Inside a fenced code block (` ``` ` / `~~~`), inline code spans
(`` `...` ``), and Markdown link URLs (the `(...)` half of
`[text](url)`), tokens are SKIPPED. URLs frequently contain
uppercase tokens that are not English acronyms (`AWS_REGION` env var,
`X-Real-IP` header) and would false-positive heavily.

Public API:

    detect_acronym_issues(text: str, *, allowlist: set[str] | None = None,
                          min_len: int = 2, min_repeats: int = 2,
                          extra_known: set[str] | None = None,
                          ) -> list[Finding]
    format_report(findings: list[Finding]) -> str

`extra_known` lets the caller pre-declare project-specific acronyms
that should be treated as always-defined (the team knows what `RPO`
means, no need to expand). `allowlist` overrides the default
universal set entirely.

Pure function over `str`; no Markdown parser, no language detection,
no networking. Single forward pass with one O(N) re-scan to compute
the cross-document expansion table.
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
    acronym: str
    sentence: str
    detail: str


_DEFAULT_ALLOWLIST = frozenset({
    "OK", "USA", "URL", "API", "JSON", "HTTP", "HTTPS", "CSS", "HTML",
    "SQL", "XML", "YAML", "CSV", "PDF", "RAM", "CPU", "GPU", "OS",
    "UI", "UX", "ID", "PR", "CI", "CD", "IO", "AM", "PM", "UTC",
    "TCP", "UDP", "DNS", "TLS", "SSL", "SSH", "FTP", "IP", "MAC",
    "USB", "PCI", "SDK", "IDE", "REST", "GRPC", "RPC", "TODO", "FAQ",
    "CEO", "CTO", "CFO", "VP", "HR", "IT", "PDF", "PNG", "JPG", "GIF",
    "SVG", "MP3", "MP4", "WAV",
})

_FENCE_RE = re.compile(r"^[ \t]*(```|~~~)")
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
_MD_LINK_URL_RE = re.compile(r"\[[^\]]*\]\(([^)]*)\)")

# Acronym candidate: 2+ uppercase letters, optionally followed by digits,
# with non-word boundaries (so `Foo` start, `BAR`, then `,` are fine but
# `XMLHttpRequest` does NOT match because `HttpRequest` has lowercase
# adjacent — we want the surrounding chars to be non-word OR start/end).
_ACRONYM_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Z]{2,}\d*)(?![A-Za-z_])")

# Sentence splitter: split on `. `, `! `, `? `, or `\n\n` keeping it
# simple. Acronym-aware (do NOT split on `e.g.` or `U.S.`) is out of
# scope — the false-split rate is low for LLM output which prefers
# spelled-out forms. We accept that.
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[\"'`])|\n\s*\n")

# Expansion patterns (case-insensitive on the long form):
#   `Long Form (ACR)` — capture (long_form, ACR)
#   `ACR (Long Form)` — capture (ACR, long_form)
_EXPAND_LONG_THEN_ACR_RE = re.compile(
    r"((?:[A-Z][a-z]+|[a-z]+)(?:[\s-][A-Za-z]+){1,8})\s+\(([A-Z]{2,}\d*)\)"
)
_EXPAND_ACR_THEN_LONG_RE = re.compile(
    r"\b([A-Z]{2,}\d*)\s+\(((?:[A-Z]?[a-z]+)(?:[\s-][A-Za-z]+){1,8})\)"
)


def _strip_inline_code_and_urls(line: str) -> str:
    """Replace inline-code spans and link URLs with same-length spaces."""
    out: list[str] = []
    last = 0
    for m in _INLINE_CODE_RE.finditer(line):
        out.append(line[last:m.start()])
        out.append(" " * (m.end() - m.start()))
        last = m.end()
    out.append(line[last:])
    s = "".join(out)
    # Now strip MD link URLs (the `(...)` half).
    out2: list[str] = []
    last = 0
    for m in _MD_LINK_URL_RE.finditer(s):
        out2.append(s[last:m.start(1)])
        out2.append(" " * (m.end(1) - m.start(1)))
        last = m.end(1)
    out2.append(s[last:])
    return "".join(out2)


def _normalize_long_form(s: str) -> str:
    return " ".join(s.lower().split())


def detect_acronym_issues(
    text: str,
    *,
    allowlist: set[str] | None = None,
    min_len: int = 2,
    min_repeats: int = 2,
    extra_known: set[str] | None = None,
) -> list[Finding]:
    if not isinstance(text, str):
        raise ValidationError(
            f"text must be str, got {type(text).__name__}"
        )

    eff_allowlist = (
        frozenset(allowlist) if allowlist is not None else _DEFAULT_ALLOWLIST
    )
    eff_extra_known = frozenset(extra_known) if extra_known else frozenset()

    # --- Phase 1: build the "scannable" view of the text with fenced
    # code, inline code, and MD link URLs masked to spaces (preserving
    # all column / offset arithmetic against the ORIGINAL text).
    lines = text.split("\n")
    if text.endswith("\n") and lines and lines[-1] == "":
        lines = lines[:-1]
    line_starts: list[int] = []
    cur = 0
    for raw in lines:
        line_starts.append(cur)
        cur += len(raw) + 1
    masked_lines: list[str] = []
    in_fence = False
    fence_char: str | None = None
    for raw in lines:
        m_fence = _FENCE_RE.match(raw)
        if m_fence:
            fc = m_fence.group(1)
            if not in_fence:
                in_fence = True
                fence_char = fc
                masked_lines.append(" " * len(raw))
                continue
            if fence_char == fc:
                in_fence = False
                fence_char = None
                masked_lines.append(" " * len(raw))
                continue
        if in_fence:
            masked_lines.append(" " * len(raw))
        else:
            masked_lines.append(_strip_inline_code_and_urls(raw))
    masked_text = "\n".join(masked_lines)

    # --- Phase 2: collect ALL acronym occurrences in masked_text with
    # their byte offsets, plus the sentence each lives in (sentences
    # are computed against the masked text so we don't accidentally
    # split a sentence on a `.` inside masked code).
    occurrences: list[tuple[str, int]] = []
    for m in _ACRONYM_RE.finditer(masked_text):
        tok = m.group(1)
        if len(tok) < min_len:
            continue
        if tok in eff_allowlist or tok in eff_extra_known:
            continue
        occurrences.append((tok, m.start()))

    # --- Phase 3: collect ALL expansion definitions in masked_text.
    # For each acronym, record every (long_form_normalized, offset)
    # pair so we can detect inconsistent re-expansion.
    expansions: dict[str, list[tuple[str, int]]] = {}
    for m in _EXPAND_LONG_THEN_ACR_RE.finditer(masked_text):
        long_form, acr = m.group(1), m.group(2)
        if acr in eff_allowlist or acr in eff_extra_known:
            continue
        expansions.setdefault(acr, []).append(
            (_normalize_long_form(long_form), m.start())
        )
    for m in _EXPAND_ACR_THEN_LONG_RE.finditer(masked_text):
        acr, long_form = m.group(1), m.group(2)
        if acr in eff_allowlist or acr in eff_extra_known:
            continue
        expansions.setdefault(acr, []).append(
            (_normalize_long_form(long_form), m.start())
        )

    # --- Phase 4: classify each acronym.
    findings: list[Finding] = []

    # First-use lookup: for each acronym, the offset of its first
    # occurrence and the offset of its first expansion (if any).
    first_use: dict[str, int] = {}
    for tok, off in occurrences:
        first_use.setdefault(tok, off)

    # `never_expanded`: for each acronym not in `expansions` and
    # appearing >= min_repeats times.
    counts: dict[str, int] = {}
    for tok, _ in occurrences:
        counts[tok] = counts.get(tok, 0) + 1

    # `undefined_first_use`: the first occurrence of each acronym is
    # before any expansion (or there is no expansion at all).
    for tok, first_off in first_use.items():
        exp_offsets = sorted(off for _, off in expansions.get(tok, []))
        # If the very first occurrence offset coincides with an
        # expansion (the expansion form `Long (ACR)` itself contains
        # the ACR token at first_off), then this IS the definition,
        # not an undefined use.
        if exp_offsets and first_off >= exp_offsets[0] - 1:
            # The acronym at first_off is part of (or after) an
            # expansion — defined.
            continue
        # Else flag undefined first use.
        line_no, col, sent = _locate(text, lines, line_starts, first_off)
        findings.append(Finding(
            kind="undefined_first_use",
            line_number=line_no,
            column=col,
            offset=first_off,
            acronym=tok,
            sentence=sent,
            detail=(
                f"acronym {tok!r} first used at byte {first_off} with no "
                f"preceding expansion in the document"
            ),
        ))
        if counts.get(tok, 0) >= min_repeats and tok not in expansions:
            findings.append(Finding(
                kind="never_expanded",
                line_number=line_no,
                column=col,
                offset=first_off,
                acronym=tok,
                sentence=sent,
                detail=(
                    f"acronym {tok!r} used {counts[tok]} times, never "
                    "expanded"
                ),
            ))

    # `inconsistent_expansion`: same acronym, multiple expansions with
    # DIFFERENT normalized long forms.
    for acr, exps in expansions.items():
        seen_long: dict[str, int] = {}
        for long_norm, off in exps:
            if long_norm not in seen_long:
                seen_long[long_norm] = off
        if len(seen_long) > 1:
            # Flag the SECOND-onward distinct expansion.
            sorted_seen = sorted(seen_long.items(), key=lambda kv: kv[1])
            first_long, _first_off = sorted_seen[0]
            for long_norm, off in sorted_seen[1:]:
                line_no, col, sent = _locate(
                    text, lines, line_starts, off
                )
                findings.append(Finding(
                    kind="inconsistent_expansion",
                    line_number=line_no,
                    column=col,
                    offset=off,
                    acronym=acr,
                    sentence=sent,
                    detail=(
                        f"acronym {acr!r} expanded as {long_norm!r} but "
                        f"earlier expanded as {first_long!r}"
                    ),
                ))

    # `redundant_re_expansion`: same acronym, same expansion long form,
    # appearing more than once.
    for acr, exps in expansions.items():
        seen: dict[str, list[int]] = {}
        for long_norm, off in exps:
            seen.setdefault(long_norm, []).append(off)
        for long_norm, offs in seen.items():
            if len(offs) > 1:
                offs_sorted = sorted(offs)
                for off in offs_sorted[1:]:
                    line_no, col, sent = _locate(
                        text, lines, line_starts, off
                    )
                    findings.append(Finding(
                        kind="redundant_re_expansion",
                        line_number=line_no,
                        column=col,
                        offset=off,
                        acronym=acr,
                        sentence=sent,
                        detail=(
                            f"acronym {acr!r} re-expanded as "
                            f"{long_norm!r} (already established)"
                        ),
                    ))

    # `lowercase_after_acronym`: a lowercased form of an acronym that
    # the doc has already introduced (uppercase) appears later as a
    # standalone word. We only flag if the lowercased form is NOT a
    # common English word — heuristic: length >= 3 AND not in a small
    # stop set. To stay deterministic and stdlib-only, we use a tiny
    # built-in stop set covering common 3-letter words that collide
    # with frequent acronyms. The conservative behavior is "only flag
    # when the doc has actually introduced the uppercase form", which
    # already eliminates most false positives.
    _STOP = {"the", "and", "for", "but", "all", "any", "you", "our", "out",
             "can", "has", "had", "was", "are", "not", "use", "one", "two",
             "saw", "old", "new", "low", "set", "let", "did"}
    for tok in counts:
        if len(tok) < 3:
            continue
        lower_form = tok.lower()
        if lower_form in _STOP:
            continue
        # Find lowercase occurrences in masked_text.
        lc_re = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(lower_form)}(?![A-Za-z0-9_])")
        first_acr_off = first_use[tok]
        for m in lc_re.finditer(masked_text):
            if m.start() < first_acr_off:
                # Lowercase appeared BEFORE the uppercase introduction
                # — that's a different problem (and probably not the
                # acronym at all). Skip.
                continue
            line_no, col, sent = _locate(text, lines, line_starts, m.start())
            findings.append(Finding(
                kind="lowercase_after_acronym",
                line_number=line_no,
                column=col,
                offset=m.start(),
                acronym=tok,
                sentence=sent,
                detail=(
                    f"lowercase {lower_form!r} appears after acronym "
                    f"{tok!r} was introduced — likely model artifact"
                ),
            ))

    findings.sort(key=lambda f: (f.offset, f.kind))
    return findings


def _locate(
    text: str,
    lines: list[str],
    line_starts: list[int],
    offset: int,
) -> tuple[int, int, str]:
    """Return (line_number_1based, column_1based, sentence_at_offset)."""
    # Binary-ish linear search — line_starts is small and sorted.
    line_no = 1
    for i, start in enumerate(line_starts):
        if start <= offset:
            line_no = i + 1
        else:
            break
    col = offset - line_starts[line_no - 1] + 1
    # Sentence: walk backward to nearest sentence start (start of doc,
    # or after `.`/`!`/`?` + space, or after blank line).
    s = max(0, offset - 200)
    e = min(len(text), offset + 200)
    window = text[s:e]
    # Find last sentence end before offset within window.
    rel = offset - s
    pre = window[:rel]
    sent_start = max(
        (pre.rfind(t) for t in (". ", "! ", "? ", "\n\n", "\n")),
        default=-1,
    )
    if sent_start == -1:
        sent_start = 0
    else:
        sent_start += 1
    post = window[rel:]
    sent_end_candidates = [
        post.find(t) for t in (". ", "! ", "? ", "\n\n", "\n")
    ]
    sent_end_candidates = [c for c in sent_end_candidates if c >= 0]
    sent_end = (
        rel + min(sent_end_candidates) + 1
        if sent_end_candidates else len(window)
    )
    sentence = window[sent_start:sent_end].strip()
    sentence = " ".join(sentence.split())
    if len(sentence) > 160:
        sentence = sentence[:157] + "..."
    return (line_no, col, sentence)


def format_report(findings: list[Finding]) -> str:
    if not findings:
        return "OK: all acronyms expanded at first use.\n"
    out = [f"FOUND {len(findings)} acronym finding(s):"]
    for f in findings:
        out.append(
            f"  [{f.kind}] line={f.line_number} col={f.column} "
            f"off={f.offset} :: {f.detail}"
        )
        out.append(f"    sentence={f.sentence!r}")
    out.append("")
    return "\n".join(out)


__all__ = [
    "Finding",
    "ValidationError",
    "detect_acronym_issues",
    "format_report",
]
