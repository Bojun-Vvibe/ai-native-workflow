#!/usr/bin/env python3
"""
Fence blank-line spacing validator for LLM-generated Markdown.

CommonMark and most production Markdown renderers (GitHub, GitLab,
pandoc with --gfm) require a blank line BEFORE and AFTER a fenced
code block (``` or ~~~) for the fence to be recognized as a block.
When that blank line is missing, the renderer either:

  * folds the fence into the surrounding paragraph (the ``` becomes
    visible literal backticks, the code is lost), or
  * eats the prior/following line as part of the fence content.

LLMs frequently glue a fence directly to the line above or below
because their training data is full of inline code-style explanations
("the function returns:```py\nreturn 1\n```now we can..."). It looks
fine in the streaming preview and breaks at render time.

This validator reports four kinds:

  * `missing_blank_before` — opening fence with non-blank prev line
  * `missing_blank_after`  — closing fence with non-blank next line
  * `extra_blank_before`   — more than one blank line before opening
  * `extra_blank_after`    — more than one blank line after closing

Pure stdlib. The first two are correctness bugs; the last two are
style noise that operators typically warn-only.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass


FENCE_RE = re.compile(r"^(\s{0,3})(`{3,}|~{3,})(.*)$")


@dataclass
class Hit:
    line_no: int
    kind: str
    detail: str


def scan(text: str) -> list[Hit]:
    lines = text.splitlines()
    hits: list[Hit] = []

    # First pass: locate fence runs as (open_idx, close_idx) pairs.
    in_fence = False
    fence_marker = ""
    open_idx = -1
    runs: list[tuple[int, int]] = []
    for i, line in enumerate(lines):
        m = FENCE_RE.match(line)
        if not in_fence:
            if m:
                in_fence = True
                fence_marker = m.group(2)[0] * 3  # normalize to 3-char prefix
                open_idx = i
        else:
            # close on a fence whose marker char matches and whose run
            # length is >= the opener's run length, with no info string
            if m and m.group(2)[0] == fence_marker[0] and m.group(3).strip() == "":
                runs.append((open_idx, i))
                in_fence = False
                fence_marker = ""
                open_idx = -1
    # Unterminated fence: out of scope for this validator (covered by
    # llm-output-orphan-fence-detector). Skip silently.

    for open_idx, close_idx in runs:
        # ---- before opening ----
        if open_idx == 0:
            pass  # start of file is fine
        else:
            prev = lines[open_idx - 1]
            if prev.strip() != "":
                hits.append(
                    Hit(
                        line_no=open_idx + 1,
                        kind="missing_blank_before",
                        detail=(
                            f"opening fence on line {open_idx + 1} has "
                            f"non-blank line {open_idx} above "
                            f"({prev[:50]!r}); CommonMark requires a blank "
                            "line before a fenced code block"
                        ),
                    )
                )
            else:
                # count consecutive blanks above
                k = open_idx - 1
                blanks = 0
                while k >= 0 and lines[k].strip() == "":
                    blanks += 1
                    k -= 1
                if blanks > 1 and k >= 0:
                    hits.append(
                        Hit(
                            line_no=open_idx + 1,
                            kind="extra_blank_before",
                            detail=(
                                f"opening fence on line {open_idx + 1} has "
                                f"{blanks} blank lines above (expected 1)"
                            ),
                        )
                    )

        # ---- after closing ----
        if close_idx == len(lines) - 1:
            pass  # end of file is fine
        else:
            nxt = lines[close_idx + 1]
            if nxt.strip() != "":
                hits.append(
                    Hit(
                        line_no=close_idx + 1,
                        kind="missing_blank_after",
                        detail=(
                            f"closing fence on line {close_idx + 1} has "
                            f"non-blank line {close_idx + 2} below "
                            f"({nxt[:50]!r}); CommonMark requires a blank "
                            "line after a fenced code block"
                        ),
                    )
                )
            else:
                k = close_idx + 1
                blanks = 0
                while k < len(lines) and lines[k].strip() == "":
                    blanks += 1
                    k += 1
                if blanks > 1 and k < len(lines):
                    hits.append(
                        Hit(
                            line_no=close_idx + 1,
                            kind="extra_blank_after",
                            detail=(
                                f"closing fence on line {close_idx + 1} has "
                                f"{blanks} blank lines below (expected 1)"
                            ),
                        )
                    )
    return hits


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] != "-":
        with open(argv[1], encoding="utf-8") as f:
            text = f.read()
    else:
        text = sys.stdin.read()
    hits = scan(text)
    for h in hits:
        print(f"line {h.line_no}: {h.kind}")
        print(f"  {h.detail}")
    # Only the two "missing" kinds are correctness bugs.
    fail = any(h.kind.startswith("missing_") for h in hits)
    if fail:
        n = sum(1 for h in hits if h.kind.startswith("missing_"))
        warn = sum(1 for h in hits if h.kind.startswith("extra_"))
        msg = f"\nFAIL: {n} fence-spacing correctness finding(s)"
        if warn:
            msg += f" (+ {warn} style finding(s))"
        print(msg)
        return 1
    if hits:
        print(f"\nWARN: {len(hits)} fence-spacing style finding(s)")
        return 0
    print("OK: fence blank-line spacing is correct")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
