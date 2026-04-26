"""Markdown link-reference-definition orphan detector for LLM output.

Pure stdlib. Scans LLM-generated Markdown for two orthogonal failure
modes around the *reference-style* link family
(``[text][label]`` / ``[text][]`` / ``[label]``) and its definitions
(``[label]: https://...``):

  - ``undefined_reference``  a link uses ``[label]`` but no
                             ``[label]: <url>`` definition exists in
                             the document. Renderer behavior diverges
                             — GitHub renders the link as literal
                             square-bracket prose; pandoc emits an
                             empty <a href> tag; some static-site
                             generators raise build errors. The model
                             often produces this when it imagined a
                             reference list that never made it to the
                             output, or when the output was truncated
                             before the definitions block.

  - ``orphan_definition``    a ``[label]: <url>`` definition exists
                             but no ``[label]`` reference uses it.
                             Common artifact when an edit removed an
                             inline reference but left the definition,
                             or when the model copied a definitions
                             block from a related document and pruned
                             only the prose. The doc still renders
                             cleanly so the bug is invisible at preview
                             time, but RAG chunkers / link checkers /
                             dead-link reports surface a "live" URL
                             that is in fact unreferenced.

  - ``duplicate_definition`` two definitions with the same label and
                             different URLs. CommonMark says the FIRST
                             definition wins; renderers vary
                             (markdown-it honors first; some legacy
                             parsers honor last). Almost always a model
                             artifact where the generator emitted the
                             same label from two different sources.

  - ``empty_label``          ``[][]`` or ``[text][]`` where the
                             collapsed-reference label resolves to an
                             empty string after normalization. Always
                             a bug — there is no way to define an
                             empty-label target in CommonMark.

  - ``label_case_mismatch``  reference uses ``[OAuth]`` but only
                             ``[oauth]: ...`` is defined. CommonMark
                             label matching is case-insensitive AND
                             whitespace-collapsing, so the link
                             resolves correctly, but the case mismatch
                             is a strong signal that the model lost
                             its own naming convention mid-document
                             and a downstream reader / linter that
                             enforces the casing convention will fail.
                             Reported as a soft warning kind.

Findings are sorted by ``(line_no, kind, label)`` so byte-identical
re-runs make diff-on-the-output a valid CI signal.

Pure function over ``str`` — no Markdown library, no networking, no
URL validation (that's a different gate). Stdlib-only Python.

Composes with:

  - ``llm-output-markdown-heading-level-skip-detector`` /
    ``llm-output-markdown-ordered-list-numbering-monotonicity-validator``
    — orthogonal Markdown-structure gates with the same ``Finding``
    shape and stable sort, so a single CI step can union them.
  - ``llm-output-url-scheme-allowlist-validator`` — the natural
    follow-up: this gate confirms references resolve to *some*
    definition; that gate confirms the URL is acceptable.
  - ``citation-id-broken-link-detector`` — sibling concept on a
    different artifact (citation IDs vs Markdown reference labels);
    same finding-shape pattern.
  - ``agent-output-validation`` — feed ``(kind, label)`` into the
    repair prompt for a one-turn fix
    (``"add a definition for [API_DOCS] or remove the reference"``).
  - ``structured-error-taxonomy`` —
    ``do_not_retry / attribution=model`` for ``undefined_reference``,
    ``orphan_definition``, ``duplicate_definition``, ``empty_label``
    (corrective-system-message fixes them; a plain retry will
    reproduce); ``label_case_mismatch`` is ``info`` and never fails
    CI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    line_no: int
    kind: str
    label: str
    detail: str


def _normalize_label(label: str) -> str:
    """CommonMark label normalization: case-fold and collapse internal
    whitespace runs to a single space, with leading/trailing
    whitespace stripped.
    """
    return re.sub(r"\s+", " ", label.strip()).casefold()


# Definition line: optional <=3-space indent, [label]: url [optional title]
# Label cannot contain unescaped ']', and the line must start the
# definition (we only honor block-level definitions; CommonMark
# requires this anyway).
_DEF_RE = re.compile(
    r"""^[ ]{0,3}
        \[
          (?P<label>(?:\\.|[^\]\\])+)
        \]:
        \s+
        (?P<dest>\S+)
        (?:\s+(?P<title>"[^"]*"|'[^']*'|\([^)]*\)))?
        \s*$""",
    re.VERBOSE,
)


# Reference link forms (all on one line for this detector — multi-line
# reference labels are legal but rare in LLM output and the
# false-positive cost of a stricter parser outweighs the recall gain).
#
#   [text][label]      full reference
#   [text][]           collapsed reference  (label == text)
#   [label]            shortcut reference   (label == text, no second [])
#
# We strip fenced code blocks and inline code spans before scanning so
# code samples that legitimately contain ``[foo]`` strings don't
# false-positive.

_FENCE_OPEN = re.compile(r"^[ ]{0,3}(```+|~~~+)")


def _strip_code(text: str) -> str:
    """Replace fenced-code-block bodies and inline `code` spans with
    runs of spaces of the same length. Preserves line offsets so
    line_no math stays correct downstream.
    """
    lines = text.split("\n")
    out_lines: list[str] = []
    in_fence = False
    fence_char = ""
    fence_run = 0
    for line in lines:
        m = _FENCE_OPEN.match(line)
        if m:
            run = m.group(1)
            ch = run[0]
            if not in_fence:
                in_fence = True
                fence_char = ch
                fence_run = len(run)
                out_lines.append(" " * len(line))
                continue
            else:
                if ch == fence_char and len(run) >= fence_run:
                    in_fence = False
                    fence_char = ""
                    fence_run = 0
                    out_lines.append(" " * len(line))
                    continue
        if in_fence:
            out_lines.append(" " * len(line))
            continue
        # Strip inline code spans on this line.
        out_lines.append(_strip_inline_code(line))
    return "\n".join(out_lines)


def _strip_inline_code(line: str) -> str:
    """Replace each backtick-delimited span with same-length spaces."""
    out = list(line)
    i = 0
    n = len(line)
    while i < n:
        if line[i] == "`":
            j = i
            while j < n and line[j] == "`":
                j += 1
            run_len = j - i
            # Look for closing run of equal length on this line.
            k = j
            while k < n:
                if line[k] == "`":
                    m = k
                    while m < n and line[m] == "`":
                        m += 1
                    if m - k == run_len:
                        for q in range(i, m):
                            out[q] = " "
                        i = m
                        break
                    else:
                        k = m
                else:
                    k += 1
            else:
                # No closer; leave the line alone past this run.
                return "".join(out)
            continue
        i += 1
    return "".join(out)


def _iter_references(masked: str):
    """Yield (line_no, kind, label, raw_form) for each reference link
    on each masked (code-stripped) line.

    kind is one of "full", "collapsed", "shortcut".
    """
    for line_no, line in enumerate(masked.split("\n"), start=1):
        # Skip definition lines themselves.
        if _DEF_RE.match(line):
            continue
        i = 0
        n = len(line)
        while i < n:
            if line[i] != "[":
                i += 1
                continue
            # Skip escaped '\['.
            if i > 0 and line[i - 1] == "\\":
                i += 1
                continue
            # Find matching ']'.
            j = i + 1
            depth = 1
            while j < n and depth > 0:
                if line[j] == "\\":
                    j += 2
                    continue
                if line[j] == "[":
                    depth += 1
                elif line[j] == "]":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if j >= n:
                break
            text = line[i + 1 : j]
            # Inline-link form ``[text](url)`` — skip.
            if j + 1 < n and line[j + 1] == "(":
                i = j + 1
                continue
            # Full reference: ``[text][label]``
            if j + 1 < n and line[j + 1] == "[":
                k = j + 2
                while k < n and line[k] != "]":
                    if line[k] == "\\":
                        k += 2
                        continue
                    k += 1
                if k >= n:
                    i = j + 1
                    continue
                label = line[j + 2 : k]
                if label == "":
                    # Collapsed reference: label == text.
                    yield (line_no, "collapsed", text, line[i : k + 1])
                else:
                    yield (line_no, "full", label, line[i : k + 1])
                i = k + 1
                continue
            # Shortcut reference: bare ``[label]`` followed by NOT '('
            # NOT '[' NOT ':'. The trailing ':' would make this a
            # definition, which we already filtered above.
            if j + 1 < n and line[j + 1] == ":":
                i = j + 1
                continue
            yield (line_no, "shortcut", text, line[i : j + 1])
            i = j + 1


def detect(text: str) -> list[Finding]:
    """Return the sorted list of findings for ``text``."""
    masked = _strip_code(text)
    findings: list[Finding] = []

    # First pass: collect definitions and detect duplicates.
    definitions: dict[str, list[tuple[int, str, str]]] = {}
    for line_no, line in enumerate(masked.split("\n"), start=1):
        m = _DEF_RE.match(line)
        if not m:
            continue
        label_raw = m.group("label")
        dest = m.group("dest")
        norm = _normalize_label(label_raw)
        definitions.setdefault(norm, []).append((line_no, label_raw, dest))

    for norm, defs in definitions.items():
        if len(defs) > 1:
            urls = {d[2] for d in defs}
            if len(urls) > 1:
                first_line = defs[0][0]
                later = ", ".join(
                    f"line {ln} -> {url}" for ln, _, url in defs[1:]
                )
                findings.append(
                    Finding(
                        line_no=first_line,
                        kind="duplicate_definition",
                        label=defs[0][1],
                        detail=(
                            f"first defined line {first_line} -> {defs[0][2]}; "
                            f"later: {later}"
                        ),
                    )
                )

    # Second pass: collect references.
    used_norms: set[str] = set()
    used_norm_to_raw: dict[str, str] = {}
    for line_no, kind, label_raw, _ in _iter_references(masked):
        norm = _normalize_label(label_raw)
        if norm == "":
            findings.append(
                Finding(
                    line_no=line_no,
                    kind="empty_label",
                    label="",
                    detail=f"empty label in {kind}-reference",
                )
            )
            continue
        used_norms.add(norm)
        used_norm_to_raw.setdefault(norm, label_raw)
        if norm not in definitions:
            findings.append(
                Finding(
                    line_no=line_no,
                    kind="undefined_reference",
                    label=label_raw,
                    detail=f"{kind}-reference with no matching definition",
                )
            )
        else:
            # Casing soft-warn: compare the raw forms after stripping
            # whitespace but WITHOUT case-folding.
            def_raw = definitions[norm][0][1]
            if (
                re.sub(r"\s+", " ", label_raw.strip())
                != re.sub(r"\s+", " ", def_raw.strip())
            ):
                findings.append(
                    Finding(
                        line_no=line_no,
                        kind="label_case_mismatch",
                        label=label_raw,
                        detail=(
                            f"reference [{label_raw}] resolves to definition "
                            f"[{def_raw}] (line {definitions[norm][0][0]}) "
                            "via case-insensitive match"
                        ),
                    )
                )

    # Orphan definitions: defined but never referenced.
    for norm, defs in definitions.items():
        if norm not in used_norms:
            line_no, label_raw, dest = defs[0]
            findings.append(
                Finding(
                    line_no=line_no,
                    kind="orphan_definition",
                    label=label_raw,
                    detail=f"definition -> {dest} is never referenced",
                )
            )

    findings.sort(key=lambda f: (f.line_no, f.kind, f.label))
    return findings


def format_report(findings: list[Finding]) -> str:
    if not findings:
        return "OK: no link-reference issues found.\n"
    lines = [f"FOUND {len(findings)} link-reference issue(s):"]
    for f in findings:
        lines.append(
            f"  line {f.line_no} kind={f.kind} label={f.label!r}: {f.detail}"
        )
    return "\n".join(lines) + "\n"
