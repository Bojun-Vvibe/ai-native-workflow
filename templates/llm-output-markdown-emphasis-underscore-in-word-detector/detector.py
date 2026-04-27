"""Pure-stdlib detector for intra-word underscores that some markdown
renderers turn into accidental emphasis.

CommonMark draws a sharp distinction between ``*`` and ``_`` for
emphasis:

- ``*`` opens/closes emphasis around any character.
- ``_`` only opens/closes emphasis at **word boundaries**. So
  ``snake_case_name`` is rendered literally — the underscores stay.

This makes ``_`` the "safe" choice for technical writing... in
CommonMark. The problem is that **not every renderer is CommonMark**:

- Original Markdown.pl, older PHP-Markdown, and many wikis happily
  treat ``snake_case`` as ``snake<em>case</em>``.
- GitHub-Flavored Markdown follows CommonMark here, but only since
  ~2017; older mirrors and offline renderers still do the wrong thing.
- Some notebook exporters (older nbconvert), some Slack/Confluence
  importers, and most static-site generators built on a non-CommonMark
  parser will italicize the middle of ``my_var_name`` and silently
  swallow the underscores in the rendered output.

The LLM failure mode: the model writes a paragraph that mentions
``user_id``, ``snake_case``, ``__init__``, or ``MAX_RETRIES`` in plain
prose (not inside backticks). The CommonMark preview looks fine, the
author ships it, and the production renderer turns it into
``user<em>id</em>`` — losing the underscores and italicizing the
wrong thing.

The fix is **always the same**: wrap identifiers in backticks. This
detector flags places where that didn't happen.

Three finding kinds:

- ``intra_word_underscore`` — an underscore appears between two
  word characters (letter / digit) outside any code span. The
  classic ``snake_case`` shape. May or may not be rendered as
  emphasis depending on renderer.
- ``leading_double_underscore_dunder`` — token of the shape
  ``__name__`` (Python dunder). High-risk: many renderers turn
  ``__init__`` into bold ``init``.
- ``mixed_underscore_word_run`` — a single contiguous word-ish
  token containing 2+ internal underscores (e.g. ``a_b_c_d``).
  Same root cause as ``intra_word_underscore`` but flagged
  separately because non-CommonMark renderers tend to mangle these
  in even uglier ways (alternating italics).

Out of scope:

- Underscores inside fenced code blocks (``` ``` ``` and ``~~~``).
- Underscores inside inline code spans (`` `like this` ``).
- Underscores inside autolinks ``<https://...>`` or
  link/image URLs ``[text](https://example.invalid/foo_bar)``.
- A bare leading ``_word`` or trailing ``word_`` outside a word
  boundary — those *can* legitimately be emphasis intent.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Iterable


_FENCE_RE = re.compile(r"^(?P<indent>[ ]{0,3})(?P<fence>`{3,}|~{3,})")

# A "word-ish" token containing at least one internal underscore between
# two word characters. Word char = [A-Za-z0-9]. We keep ASCII-only on
# purpose; non-ASCII identifiers are vanishingly rare in tech prose
# and we don't want to chase Unicode word-boundary edge cases.
_WORD_UNDERSCORE_RE = re.compile(r"[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+")

# Python-style dunder: __name__ (exactly two leading + two trailing
# underscores, word chars in between).
_DUNDER_RE = re.compile(r"__[A-Za-z0-9]+(?:_[A-Za-z0-9]+)*__")


@dataclass(frozen=True)
class Finding:
    kind: str
    line: int          # 1-indexed
    col: int           # 1-indexed, byte/char position in the line
    token: str
    note: str

    def format(self) -> str:
        return f"  [{self.kind}] line={self.line} col={self.col} token={self.token!r} :: {self.note}"


def _mask_inline_code_and_links(line: str) -> str:
    """Replace inline code spans, autolinks, and URL portions of links
    with spaces so their internal underscores don't trip the regex.

    We preserve column positions by replacing rather than deleting.
    """
    out = list(line)
    n = len(line)
    i = 0
    while i < n:
        c = line[i]
        # Inline code span: backtick run. Match closing run of the same length.
        if c == "`":
            j = i
            while j < n and line[j] == "`":
                j += 1
            run_len = j - i
            run = "`" * run_len
            close_idx = line.find(run, j)
            if close_idx != -1:
                # Mask everything from i through close_idx + run_len - 1.
                end = close_idx + run_len
                for k in range(i, end):
                    out[k] = " "
                i = end
                continue
            # Unclosed — leave as-is; underscores after will still match
            # but that mirrors how a real renderer would behave.
            i = j
            continue
        # Autolink: <scheme://...> or <user@host>.
        if c == "<":
            close = line.find(">", i + 1)
            if close != -1:
                inner = line[i + 1 : close]
                if (
                    "://" in inner
                    or inner.startswith(("http:", "https:", "ftp:", "mailto:"))
                    or ("@" in inner and " " not in inner and ":" not in inner)
                ):
                    for k in range(i, close + 1):
                        out[k] = " "
                    i = close + 1
                    continue
            i += 1
            continue
        # Inline link / image: ...](url) or ...](url "title")
        if c == "]" and i + 1 < n and line[i + 1] == "(":
            # Find matching ')' allowing balanced parens up to one level.
            depth = 0
            k = i + 1
            close = -1
            while k < n:
                ch = line[k]
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        close = k
                        break
                k += 1
            if close != -1:
                # Mask the (url ...) portion, keep the ] in place.
                for kk in range(i + 1, close + 1):
                    out[kk] = " "
                i = close + 1
                continue
            i += 1
            continue
        i += 1
    return "".join(out)


def detect_intra_word_underscores(text: str) -> list[Finding]:
    """Return a finding for every risky underscore-bearing token outside
    code spans, fenced code blocks, autolinks, and link URLs.
    """
    findings: list[Finding] = []
    in_fence = False
    fence_marker = ""
    fence_indent = 0

    for line_num, raw_line in enumerate(text.splitlines(), start=1):
        m_fence = _FENCE_RE.match(raw_line)
        if m_fence:
            marker = m_fence.group("fence")
            indent = len(m_fence.group("indent"))
            if not in_fence:
                in_fence = True
                fence_marker = marker[0]
                fence_indent = indent
                continue
            if marker[0] == fence_marker and abs(indent - fence_indent) <= 3:
                in_fence = False
                fence_marker = ""
                fence_indent = 0
                continue

        if in_fence:
            continue

        # Skip indented code blocks (4-space / tab lead).
        if raw_line.startswith("    ") or raw_line.startswith("\t"):
            continue

        masked = _mask_inline_code_and_links(raw_line)

        # Pass 1: dunders (most dangerous; report first).
        dunder_spans: list[tuple[int, int]] = []
        for m in _DUNDER_RE.finditer(masked):
            findings.append(
                Finding(
                    kind="leading_double_underscore_dunder",
                    line=line_num,
                    col=m.start() + 1,
                    token=m.group(0),
                    note="dunder pattern '__name__' often renders as bold 'name' in non-CommonMark renderers",
                )
            )
            dunder_spans.append((m.start(), m.end()))

        # Pass 2: word-underscore tokens (exclude ones already covered by dunders).
        for m in _WORD_UNDERSCORE_RE.finditer(masked):
            if any(ds <= m.start() and m.end() <= de for ds, de in dunder_spans):
                continue
            token = m.group(0)
            underscore_count = token.count("_")
            if underscore_count >= 2:
                kind = "mixed_underscore_word_run"
                note = (
                    f"{underscore_count} internal underscores; non-CommonMark renderers may "
                    f"alternate italics across the token"
                )
            else:
                kind = "intra_word_underscore"
                note = "intra-word underscore may render as emphasis in non-CommonMark renderers; wrap in backticks"
            findings.append(
                Finding(
                    kind=kind,
                    line=line_num,
                    col=m.start() + 1,
                    token=token,
                    note=note,
                )
            )

    # Stable order: by (line, col).
    findings.sort(key=lambda f: (f.line, f.col))
    return findings


def format_report(findings: Iterable[Finding]) -> str:
    findings = list(findings)
    if not findings:
        return "OK: no risky intra-word underscores found."
    lines = [f"FOUND {len(findings)} intra-word-underscore finding(s):"]
    lines.extend(f.format() for f in findings)
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        text = sys.stdin.read()
    else:
        with open(argv[1], "r", encoding="utf-8") as f:
            text = f.read()
    findings = detect_intra_word_underscores(text)
    print(format_report(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
