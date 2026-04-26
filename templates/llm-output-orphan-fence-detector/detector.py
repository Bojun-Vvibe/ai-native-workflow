"""Pure-stdlib detector for orphan Markdown code fences in LLM output.

A common LLM artifact: the model opens a fenced code block with ``` or
~~~, emits some content, and then either runs out of token budget or
"forgets" to close the fence. The opposite also happens: a stray closing
fence with no matching opener (often from a bad copy/paste or a
truncated continuation). Both shapes are pernicious because every
downstream Markdown renderer reacts differently — some swallow the rest
of the document into a code block, others bleed `</code>` into prose.

Three finding kinds:

- `unclosed_fence` — an opening fence with no matching closer before
  EOF. Reported on the opening line.
- `orphan_closing_fence` — a closing fence that does not match any
  open fence (i.e. fence depth would go negative). Reported on the
  offending line.
- `mismatched_fence_char` — an opening ``` closed by ~~~ or vice
  versa. The Markdown spec requires the closer to use the same fence
  character as the opener; mixing them is a silent bug.

Indentation up to 3 spaces is permitted on a fence (per CommonMark).
Anything indented 4+ spaces is a code block by indentation, not a
fence, so we ignore it.

Usage:
    python3 detector.py [FILE ...]   # files, or stdin if none
    exit 0 = clean, exit 1 = findings (JSON on stdout)
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, asdict

# A fence is 3+ backticks or 3+ tildes, optionally indented up to 3 spaces,
# optionally followed by an info string. The fence char + length determine
# what can close it: same char, length >= opener.
FENCE_RE = re.compile(r"^(?P<indent> {0,3})(?P<fence>`{3,}|~{3,})(?P<info>.*)$")


@dataclass(frozen=True)
class Finding:
    kind: str
    line_number: int
    fence_char: str
    fence_len: int
    raw_line: str

    def to_dict(self) -> dict:
        return asdict(self)


def detect_orphan_fences(text: str) -> list[Finding]:
    if not isinstance(text, str):
        raise TypeError("text must be str")
    findings: list[Finding] = []
    # Stack of open fences: (fence_char, fence_len, line_number, raw_line)
    stack: list[tuple[str, int, int, str]] = []

    for lineno, raw in enumerate(text.splitlines(), start=1):
        m = FENCE_RE.match(raw)
        if not m:
            continue
        fence = m.group("fence")
        info = m.group("info")
        fence_char = fence[0]
        fence_len = len(fence)

        if stack:
            # We're inside a fence. A line closes the fence iff:
            #   - it has no info string (only whitespace allowed after),
            #   - same fence char as the opener,
            #   - length >= opener length.
            open_char, open_len, _, _ = stack[-1]
            info_clean = info.strip(" \t")
            if info_clean == "" and fence_len >= open_len:
                if fence_char == open_char:
                    stack.pop()
                    continue
                # Same shape (no info string) but different char: that's a
                # mismatch attempt. We DON'T pop — the opener stays open —
                # but we flag it because a human reader will be confused.
                findings.append(
                    Finding(
                        kind="mismatched_fence_char",
                        line_number=lineno,
                        fence_char=fence_char,
                        fence_len=fence_len,
                        raw_line=raw,
                    )
                )
                continue
            # Inside a fence and the line isn't a valid closer — it's
            # just content. Skip.
            continue

        # Not inside a fence. This line opens a new one.
        stack.append((fence_char, fence_len, lineno, raw))

    # Anything left on the stack is unclosed.
    for fence_char, fence_len, lineno, raw in stack:
        findings.append(
            Finding(
                kind="unclosed_fence",
                line_number=lineno,
                fence_char=fence_char,
                fence_len=fence_len,
                raw_line=raw,
            )
        )

    # Note: orphan_closing_fence is naturally caught by the "open a new
    # one" branch above when a closer appears with no opener — it'll be
    # treated as an opener and then reported as unclosed. To distinguish
    # the two cases properly, we re-walk: a fence line with NO info
    # string that appears at the top level (stack empty) is structurally
    # ambiguous — could be a deliberate empty-info opener or a stray
    # closer. We mark it as orphan_closing_fence ONLY if it's also the
    # final unclosed entry AND has no info string AND is followed by
    # plain prose (i.e. there's at least one non-fence line after it
    # that doesn't look like code). That heuristic is too noisy; we
    # instead reclassify any unclosed fence whose info string is empty
    # AND whose body would be empty (no content lines after it before
    # EOF) as an orphan closer. See README "Limitations".
    reclassified: list[Finding] = []
    lines = text.splitlines()
    for f in findings:
        if f.kind != "unclosed_fence":
            reclassified.append(f)
            continue
        # Look at the info string and trailing content.
        m = FENCE_RE.match(f.raw_line)
        info = m.group("info").strip(" \t") if m else ""
        trailing = lines[f.line_number:]  # lines AFTER the fence line
        nonblank = [ln for ln in trailing if ln.strip() != ""]
        if info == "" and len(nonblank) == 0:
            reclassified.append(
                Finding(
                    kind="orphan_closing_fence",
                    line_number=f.line_number,
                    fence_char=f.fence_char,
                    fence_len=f.fence_len,
                    raw_line=f.raw_line,
                )
            )
        else:
            reclassified.append(f)

    return reclassified


def _read_inputs(argv: list[str]) -> str:
    if len(argv) <= 1:
        return sys.stdin.read()
    chunks = []
    for path in argv[1:]:
        with open(path, "r", encoding="utf-8") as fh:
            chunks.append(fh.read())
    return "\n".join(chunks)


def main(argv: list[str]) -> int:
    text = _read_inputs(argv)
    findings = detect_orphan_fences(text)
    payload = {
        "findings": [f.to_dict() for f in findings],
        "count": len(findings),
        "ok": len(findings) == 0,
    }
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
