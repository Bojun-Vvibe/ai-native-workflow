"""Pure stdlib validator for blank-line discipline around Markdown
fenced code blocks in LLM output.

CommonMark says a fenced code block does not strictly require a blank
line before it, but the *practical* rule (enforced by GitHub's
renderer, by `markdownlint` rule MD031, by Prettier, and by every
static-site generator that runs Markdown through a paragraph parser
first) is:

    A fenced code block MUST have a blank line BEFORE its opening
    fence and AFTER its closing fence, unless it is at the very
    start or end of the document, or inside a list item where it
    is the first/last block.

When the LLM emits a fence with no blank line above, three things
break in production: (a) GitHub silently renders the fence as a
literal triple-backtick string inside the preceding paragraph, (b)
RAG chunkers that split on blank lines glue prose and code into one
chunk that the embedder can't tag, (c) `pandoc` and many static-site
generators emit a different (and less-readable) HTML structure.

Four finding kinds, all per-fence:

  - missing_blank_before :: fence opener immediately follows a
                            non-blank, non-fence-opener line, and is
                            not at the start of the document or the
                            first block in a list item.
  - missing_blank_after  :: fence closer is immediately followed by
                            a non-blank, non-fence-opener line, and
                            is not at the end of the document.
  - unclosed_fence       :: fence opens and reaches end of input
                            without a matching closer (well-known
                            failure mode of LLMs that hit max_tokens
                            mid-code-block).
  - mismatched_fence_char :: fence opens with ``` but a candidate
                            closer uses ~~~, or vice versa — the
                            closer is silently treated as code body
                            so the next paragraph becomes part of
                            the block.

Public API:

    validate_fence_blank_lines(
        text: str,
        *,
        allow_in_list_item: bool = True,
    ) -> list[Finding]

    format_report(findings: list[Finding]) -> str

Pure function: no I/O, no markdown library, no regex backtracking
hazards. The only state is a tiny per-fence stack.
"""

from __future__ import annotations

from dataclasses import dataclass


class ValidationError(ValueError):
    """Raised on input that is not a `str`."""


@dataclass(frozen=True)
class Finding:
    kind: str
    line_no: int  # 1-based
    detail: str
    sample: str  # the offending line, no trailing newline


# ---------------------------------------------------------------------------
# Tokenizer helpers
# ---------------------------------------------------------------------------


def _leading_spaces(line: str) -> int:
    n = 0
    for ch in line:
        if ch == " ":
            n += 1
        elif ch == "\t":
            n += 4 - (n % 4)
        else:
            break
    return n


def _is_blank(line: str) -> bool:
    return line.strip() == ""


def _fence_open(line: str) -> tuple[str, int, int] | None:
    """Return (char, run_length, indent) if line opens a fence, else None.

    CommonMark: opener is a run of >=3 of the same char (` or ~), with
    indent <= 3 spaces, optional info string after.
    """
    indent = _leading_spaces(line)
    if indent > 3:
        return None
    s = line[indent:]
    if s.startswith("```"):
        ch = "`"
    elif s.startswith("~~~"):
        ch = "~"
    else:
        return None
    n = 0
    while n < len(s) and s[n] == ch:
        n += 1
    if n < 3:
        return None
    return ch, n, indent


def _fence_close_candidate(line: str, opener_char: str, opener_run: int) -> tuple[bool, str | None]:
    """Return (is_close, mismatched_char_if_any).

    A valid closer:
      - same char as opener
      - run length >= opener's run length
      - no info string after the run (only whitespace)
      - indent <= 3 spaces
    A 'mismatched_fence_char' candidate is a line that *looks like* a
    fence opener/closer using the OPPOSITE char with the same length
    discipline; we report it because the model probably meant to
    close.
    """
    indent = _leading_spaces(line)
    if indent > 3:
        return False, None
    s = line[indent:]
    if not s:
        return False, None

    if s[0] == opener_char:
        n = 0
        while n < len(s) and s[n] == opener_char:
            n += 1
        rest = s[n:].rstrip()
        if n >= opener_run and rest == "":
            return True, None
        return False, None

    other = "~" if opener_char == "`" else "`"
    if s[0] == other:
        n = 0
        while n < len(s) and s[n] == other:
            n += 1
        rest = s[n:].rstrip()
        if n >= 3 and rest == "":
            return False, other
    return False, None


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def _is_list_item(line: str) -> bool:
    s = line.lstrip(" \t")
    if not s:
        return False
    if s[0] in ("-", "*", "+") and (len(s) == 1 or s[1] == " "):
        return True
    # Ordered list: digits then . or ) then space
    i = 0
    while i < len(s) and s[i].isdigit():
        i += 1
    if 0 < i < len(s) and s[i] in (".", ")"):
        rest = s[i + 1 :]
        if rest.startswith(" ") or rest == "":
            return True
    return False


def validate_fence_blank_lines(
    text: str,
    *,
    allow_in_list_item: bool = True,
) -> list[Finding]:
    if not isinstance(text, str):
        raise ValidationError(f"text must be str, got {type(text).__name__}")

    findings: list[Finding] = []
    lines = text.splitlines()
    n_lines = len(lines)

    i = 0
    while i < n_lines:
        line = lines[i]
        opened = _fence_open(line)
        if opened is None:
            i += 1
            continue

        char, run, _indent = opened
        opener_line = i + 1  # 1-based

        # missing_blank_before check
        if i > 0:
            prev = lines[i - 1]
            if not _is_blank(prev):
                exempt = False
                if allow_in_list_item and _is_list_item(prev):
                    # Fence is the first block inside a list item.
                    exempt = True
                if not exempt:
                    findings.append(
                        Finding(
                            kind="missing_blank_before",
                            line_no=opener_line,
                            detail=(
                                "fence opener has no blank line above; "
                                f"prior line {i} is non-blank prose "
                                "(renderers may glue the fence into the "
                                "preceding paragraph)"
                            ),
                            sample=line.rstrip("\n"),
                        )
                    )

        # Walk forward to find the closer.
        j = i + 1
        closed_at = -1
        mismatched_lines: list[int] = []
        while j < n_lines:
            inner = lines[j]
            is_close, mismatched = _fence_close_candidate(inner, char, run)
            if is_close:
                closed_at = j
                break
            if mismatched is not None:
                mismatched_lines.append(j + 1)
            j += 1

        if closed_at == -1:
            findings.append(
                Finding(
                    kind="unclosed_fence",
                    line_no=opener_line,
                    detail=(
                        f"fence opened with {char * run!r} at line "
                        f"{opener_line} but no matching closer found "
                        "before end of input"
                    ),
                    sample=line.rstrip("\n"),
                )
            )
            for m_line in mismatched_lines:
                other = "~" if char == "`" else "`"
                findings.append(
                    Finding(
                        kind="mismatched_fence_char",
                        line_no=m_line,
                        detail=(
                            f"line uses {other!r} fence char but block "
                            f"opened with {char!r} at line {opener_line} "
                            "(probably meant to close)"
                        ),
                        sample=lines[m_line - 1].rstrip("\n"),
                    )
                )
            # Past unclosed: stop scanning.
            break

        # Closed normally. missing_blank_after check.
        if closed_at + 1 < n_lines:
            after = lines[closed_at + 1]
            if not _is_blank(after):
                # If next line is itself a fence opener, the absence of
                # blank line is still a bug (two adjacent fences with
                # no blank between them confuse parsers).
                findings.append(
                    Finding(
                        kind="missing_blank_after",
                        line_no=closed_at + 1,
                        detail=(
                            "fence closer has no blank line below; "
                            f"line {closed_at + 2} is non-blank "
                            "(renderers may glue following content "
                            "into the code block)"
                        ),
                        sample=lines[closed_at].rstrip("\n"),
                    )
                )

        # Report mismatched chars seen inside the body even when the
        # block did eventually close — they are a smell.
        for m_line in mismatched_lines:
            other = "~" if char == "`" else "`"
            findings.append(
                Finding(
                    kind="mismatched_fence_char",
                    line_no=m_line,
                    detail=(
                        f"line uses {other!r} fence char inside a block "
                        f"opened with {char!r} at line {opener_line} "
                        "(treated as code body; if a closer was intended "
                        "the block extends past where you meant)"
                    ),
                    sample=lines[m_line - 1].rstrip("\n"),
                )
            )

        i = closed_at + 1

    return findings


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------


def format_report(findings: list[Finding]) -> str:
    if not findings:
        return "OK: fenced code blocks have proper blank-line discipline.\n"
    findings = sorted(findings, key=lambda f: (f.line_no, f.kind))
    out = [f"FOUND {len(findings)} fence finding(s):"]
    for f in findings:
        out.append(f"  [{f.kind}] line={f.line_no} :: {f.detail}")
        out.append(f"    | {f.sample}")
    return "\n".join(out) + "\n"
