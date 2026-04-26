"""Pure-stdlib detector for redundant (3+) consecutive blank lines in an
LLM Markdown / prose output blob.

CommonMark and every Markdown renderer in production collapse any run of
two-or-more blank lines into the *same* visual gap as a single blank
line. So a model that emits 3, 4, 7 consecutive blank lines is producing
bytes that have NO visual effect — but those bytes do:

  - inflate token counts on the next turn (the model re-reads the
    transcript and pays for the whitespace)
  - confuse later pipeline steps that split on `\\n\\n` paragraphs
    (a 5-blank-line run yields 4 empty paragraphs, which then trip
    "empty section" / "missing body" downstream validators)
  - bloat `git diff` and PR descriptions with whitespace-only churn
    when the model regenerates a doc and the blank-run count drifts
    from 3 to 4 with no other change

A "blank line" here is a line whose content is empty OR consists
exclusively of horizontal whitespace (`" "`, `\\t`). The detector treats
both as blank because a render engine does — and a `" \\n"` line is the
even more invisible variant: not visible in the source, not visible in
the render, still costs a token.

Findings:

  - `redundant_blank_run` — a run of `>= max_allowed_blanks + 1`
    consecutive blank lines. One finding per RUN, anchored at the
    1-based line number of the FIRST blank line in the run, with the
    run length in `detail`. `max_allowed_blanks` defaults to 1
    (i.e. fire on 2+ consecutive blank lines being treated as
    excess; the default flags any run of 2 or more — see below).
  - `whitespace_only_blank` — a blank line that is not empty but is
    all-whitespace (`" "`, `\\t`, mixed). Reported per occurrence.
    Distinct from `redundant_blank_run` because the fix is different:
    `redundant_blank_run` is "delete N lines", `whitespace_only_blank`
    is "trim this one line".
  - `leading_blank` — the blob begins with one or more blank lines.
    Reported once with the leading-blank count. A model that opens
    a response with a blank line is leaking a chat template artifact.
  - `trailing_blank_run` — the blob ends with `>= 2` blank lines
    before EOF. Reported once with the trailing-blank count. POSIX
    text convention is exactly one trailing newline (rendered as
    zero blank lines after the last content line).

The `max_allowed_blanks` parameter sets the threshold for a run to be
considered redundant: with the default `max_allowed_blanks=1`, runs of
2 or more blank lines fire. Set `max_allowed_blanks=2` to allow up to
2 consecutive blanks (CommonMark-permissive: only 3+ fire). Set to 0
to forbid any blank lines at all (a strict "no blank lines" policy
for compact log output).

Pure: input is `str`, no I/O, no third-party deps, no Markdown parser.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


class ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Finding:
    kind: str
    line_number: int
    detail: str


_KINDS = (
    "leading_blank",
    "redundant_blank_run",
    "whitespace_only_blank",
    "trailing_blank_run",
)


def _is_blank(line: str) -> bool:
    """Return True if line is empty or contains only horizontal whitespace."""
    if line == "":
        return True
    for ch in line:
        if ch not in (" ", "\t"):
            return False
    return True


def _is_whitespace_only(line: str) -> bool:
    """Return True if line is non-empty AND only horizontal whitespace."""
    return line != "" and _is_blank(line)


def detect_redundant_blank_lines(
    text: str, *, max_allowed_blanks: int = 1
) -> List[Finding]:
    """Detect redundant consecutive blank lines in `text`.

    Args:
      text: The LLM output blob to scan.
      max_allowed_blanks: Maximum allowed consecutive blank lines before
        a run is considered redundant. Default 1 (so a run of 2+ fires).
        Set to 2 for CommonMark-permissive (only 3+ fires). Set to 0
        for "no blank lines at all".

    Returns:
      Sorted list of Finding records (stable sort by (line_number, kind)).
    """
    if not isinstance(text, str):
        raise ValidationError(f"text must be str, got {type(text).__name__}")
    if not isinstance(max_allowed_blanks, int) or isinstance(max_allowed_blanks, bool):
        raise ValidationError(
            f"max_allowed_blanks must be int, got {type(max_allowed_blanks).__name__}"
        )
    if max_allowed_blanks < 0:
        raise ValidationError(
            f"max_allowed_blanks must be >= 0, got {max_allowed_blanks}"
        )

    findings: List[Finding] = []
    if text == "":
        return findings

    # Split on \n; the final empty element after a trailing \n means
    # "the blob ends with a newline" — we drop it so trailing_blank_run
    # measures content blanks, not the final newline itself.
    raw_lines = text.split("\n")
    has_trailing_newline = raw_lines[-1] == ""
    lines = raw_lines[:-1] if has_trailing_newline else raw_lines

    if not lines:
        # text was just newlines (e.g. "\n", "\n\n\n")
        if has_trailing_newline and len(raw_lines) - 1 >= 2:
            findings.append(
                Finding(
                    kind="leading_blank",
                    line_number=1,
                    detail=f"blob is {len(raw_lines) - 1} blank line(s) only",
                )
            )
        return findings

    # leading_blank: count blank lines from the start
    leading = 0
    for ln in lines:
        if _is_blank(ln):
            leading += 1
        else:
            break
    if leading > 0:
        findings.append(
            Finding(
                kind="leading_blank",
                line_number=1,
                detail=f"blob opens with {leading} blank line(s)",
            )
        )

    # whitespace_only_blank: per occurrence
    for idx, ln in enumerate(lines, start=1):
        if _is_whitespace_only(ln):
            # describe what the whitespace is
            spaces = ln.count(" ")
            tabs = ln.count("\t")
            findings.append(
                Finding(
                    kind="whitespace_only_blank",
                    line_number=idx,
                    detail=f"blank line is whitespace-only (spaces={spaces}, tabs={tabs})",
                )
            )

    # redundant_blank_run: per run of `> max_allowed_blanks` consecutive blanks
    threshold = max_allowed_blanks + 1
    run_start = None
    run_len = 0
    # We don't want the leading run (already reported as leading_blank)
    # to ALSO be reported as redundant_blank_run, and we don't want the
    # trailing run (reported as trailing_blank_run below) to be reported
    # as redundant either. Track those boundaries.
    n = len(lines)
    # trailing run length
    trailing = 0
    for ln in reversed(lines):
        if _is_blank(ln):
            trailing += 1
        else:
            break

    interior_start = leading  # index (0-based) of first non-leading position
    interior_end = n - trailing  # exclusive

    i = interior_start
    while i < interior_end:
        if _is_blank(lines[i]):
            run_start = i
            run_len = 0
            while i < interior_end and _is_blank(lines[i]):
                run_len += 1
                i += 1
            if run_len >= threshold:
                findings.append(
                    Finding(
                        kind="redundant_blank_run",
                        line_number=run_start + 1,
                        detail=(
                            f"run of {run_len} consecutive blank line(s) "
                            f"(allowed: {max_allowed_blanks})"
                        ),
                    )
                )
        else:
            i += 1

    # trailing_blank_run: report when >= 2 trailing blanks
    # (one trailing blank line is just "the file ends with one newline
    # after the last content line", which is POSIX-normal.)
    if trailing >= 2:
        findings.append(
            Finding(
                kind="trailing_blank_run",
                line_number=n - trailing + 1,
                detail=f"blob ends with {trailing} blank line(s) before EOF",
            )
        )

    findings.sort(
        key=lambda f: (
            f.line_number,
            _KINDS.index(f.kind) if f.kind in _KINDS else 99,
        )
    )
    return findings


def format_report(findings: List[Finding]) -> str:
    if not findings:
        return "OK: no redundant blank lines.\n"
    lines = [f"FOUND {len(findings)} blank-line finding(s):"]
    for f in findings:
        lines.append(f"  [{f.kind}] line={f.line_number} :: {f.detail}")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "Finding",
    "ValidationError",
    "detect_redundant_blank_lines",
    "format_report",
]
