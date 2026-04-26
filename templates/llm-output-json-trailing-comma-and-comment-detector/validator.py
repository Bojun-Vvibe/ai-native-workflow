"""
llm-output-json-trailing-comma-and-comment-detector
===================================================

Pure-stdlib detector for JSONC artifacts that leak into output that is
supposed to be strict JSON: trailing commas before ``]`` / ``}``, and
``//`` line / ``/* ... */`` block comments.

This is the single most common reason a model's "JSON" reply fails
``json.loads`` despite parsing fine in a linter that allows JSONC. It
deserves its own focused detector rather than being lumped into a
generic "json invalid" branch, because:

- the *fix* is mechanical (strip the comments, trim the comma) and a
  one-shot repair prompt with the exact offset is much cheaper than
  asking the model to re-emit;
- distinguishing trailing-comma drift from genuine schema violations
  prevents the repair loop from chasing the wrong bug.

The detector is **lexer-only**, not a parser. It walks the input
once, tracks whether we are inside a string (with proper backslash
escaping), and reports artifacts with line + column + offset.

Pure function over a string. No I/O. Stdlib-only.
"""

from __future__ import annotations

from dataclasses import dataclass


# --- finding kinds ---------------------------------------------------------

KIND_TRAILING_COMMA_OBJECT = "trailing_comma_object"  # ``,}``
KIND_TRAILING_COMMA_ARRAY = "trailing_comma_array"    # ``,]``
KIND_LINE_COMMENT = "line_comment"                    # ``// ...``
KIND_BLOCK_COMMENT = "block_comment"                  # ``/* ... */``
KIND_UNTERMINATED_BLOCK_COMMENT = "unterminated_block_comment"


@dataclass(frozen=True)
class Finding:
    offset: int
    line_no: int
    column: int
    kind: str
    snippet: str   # short literal slice for the report


def _line_col(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    last_nl = text.rfind("\n", 0, offset)
    col = offset - (last_nl + 1) + 1
    return line, col


def _short(text: str, start: int, end: int, width: int = 24) -> str:
    """Return a single-line snippet around [start, end), escaping newlines."""
    s = text[start:end]
    if len(s) > width:
        s = s[: width - 1] + "…"
    return s.replace("\n", "\\n").replace("\t", "\\t")


# --- public API ------------------------------------------------------------

def detect_jsonc_artifacts(text: str) -> list[Finding]:
    """
    Walk ``text`` once and report every JSONC artifact.

    Returns: list[Finding] sorted by offset. Stable across re-runs.
    """
    findings: list[Finding] = []
    n = len(text)
    i = 0
    in_string = False
    while i < n:
        ch = text[i]

        # string handling: respect backslash escapes; ignore everything inside
        if in_string:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == '"':
                in_string = False
                i += 1
                continue
            i += 1
            continue

        if ch == '"':
            in_string = True
            i += 1
            continue

        # // line comment
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            start = i
            eol = text.find("\n", i)
            end = n if eol == -1 else eol
            line, col = _line_col(text, start)
            findings.append(
                Finding(
                    offset=start,
                    line_no=line,
                    column=col,
                    kind=KIND_LINE_COMMENT,
                    snippet=_short(text, start, end),
                )
            )
            i = end
            continue

        # /* block comment */
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            start = i
            close = text.find("*/", i + 2)
            line, col = _line_col(text, start)
            if close == -1:
                findings.append(
                    Finding(
                        offset=start,
                        line_no=line,
                        column=col,
                        kind=KIND_UNTERMINATED_BLOCK_COMMENT,
                        snippet=_short(text, start, min(start + 24, n)),
                    )
                )
                break  # rest of input is consumed by an unterminated comment
            findings.append(
                Finding(
                    offset=start,
                    line_no=line,
                    column=col,
                    kind=KIND_BLOCK_COMMENT,
                    snippet=_short(text, start, close + 2),
                )
            )
            i = close + 2
            continue

        # trailing comma: comma followed by optional whitespace then ] or }
        if ch == ",":
            j = i + 1
            while j < n and text[j] in " \t\n\r":
                j += 1
            if j < n and text[j] in "]}":
                line, col = _line_col(text, i)
                kind = (
                    KIND_TRAILING_COMMA_OBJECT
                    if text[j] == "}"
                    else KIND_TRAILING_COMMA_ARRAY
                )
                findings.append(
                    Finding(
                        offset=i,
                        line_no=line,
                        column=col,
                        kind=kind,
                        snippet=_short(text, i, j + 1),
                    )
                )
                i = j   # skip the whitespace; do not consume the bracket
                continue
            i += 1
            continue

        i += 1

    findings.sort(key=lambda f: f.offset)
    return findings


def format_report(findings: list[Finding]) -> str:
    if not findings:
        return "OK: no JSONC artifacts found."
    lines = [f"FOUND {len(findings)} JSONC artifact(s):"]
    for f in findings:
        lines.append(
            f"  line {f.line_no} col {f.column} offset {f.offset}: "
            f"kind={f.kind} {f.snippet!r}"
        )
    return "\n".join(lines)


def strip_artifacts(text: str) -> tuple[str, list[Finding]]:
    """
    Best-effort one-shot repair: returns (cleaned_text, findings).

    - Comments are deleted (line comments through end-of-line; block
      comments including their delimiters).
    - Trailing commas are deleted.
    - Unterminated block comments are NOT touched (returned in
      findings; caller should reject the input rather than guess).

    The cleaned text is **not guaranteed** to be valid JSON — only
    that these specific artifacts are gone. Caller still runs
    ``json.loads`` and treats failure as a real schema problem.
    """
    findings = detect_jsonc_artifacts(text)
    if not findings:
        return text, findings
    if any(f.kind == KIND_UNTERMINATED_BLOCK_COMMENT for f in findings):
        return text, findings

    # Build a deletion map: list of (start, end) ranges to drop.
    deletions: list[tuple[int, int]] = []
    n = len(text)
    for f in findings:
        if f.kind == KIND_LINE_COMMENT:
            eol = text.find("\n", f.offset)
            end = n if eol == -1 else eol
            deletions.append((f.offset, end))
        elif f.kind == KIND_BLOCK_COMMENT:
            close = text.find("*/", f.offset + 2)
            deletions.append((f.offset, close + 2))
        elif f.kind in (KIND_TRAILING_COMMA_OBJECT, KIND_TRAILING_COMMA_ARRAY):
            deletions.append((f.offset, f.offset + 1))

    deletions.sort()
    out = []
    cursor = 0
    for start, end in deletions:
        if start < cursor:
            continue
        out.append(text[cursor:start])
        cursor = end
    out.append(text[cursor:])
    return "".join(out), findings
