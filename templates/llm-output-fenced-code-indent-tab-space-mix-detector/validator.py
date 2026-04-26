"""Detect mixed tab/space indentation inside fenced Markdown code blocks.

Pure-stdlib. Scans a Markdown document, walks each fenced code block, and
reports per-block indent regimes. Findings fall in three classes:

    mixed_in_block         the same block uses both tab-indented lines
                           and space-indented lines
    mixed_in_line          a single indent run mixes tabs and spaces
                           (e.g. "\\t    x = 1") -- this is the form that
                           silently breaks Python and YAML
    inconsistent_in_doc    different blocks in the same document use
                           different indent regimes (one block tabs-only,
                           another spaces-only)

The detector is conservative: code blocks whose info string declares a
language where mixed indent is standard (e.g. ``make``) are skipped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

# Languages where leading tabs are required or idiomatic. Blocks tagged
# as one of these are skipped wholesale.
_TAB_REQUIRED_LANGS = frozenset({"make", "makefile", "mk", "go", "golang"})

_FENCE_RE = re.compile(r"^(?P<indent>[ ]{0,3})(?P<fence>`{3,}|~{3,})\s*(?P<info>[^\r\n]*)$")


@dataclass(frozen=True)
class Finding:
    kind: str
    block_index: int          # 0-based block ordinal in the document
    block_start_line: int     # 1-based line of the opening fence
    line_no: int              # 1-based line number of the offending line (0 for doc-level)
    detail: str
    info_string: str


@dataclass
class _Block:
    index: int
    start_line: int
    info: str
    lang: str
    lines: list[tuple[int, str]] = field(default_factory=list)  # (line_no, raw_line)


def _iter_blocks(text: str) -> Iterable[_Block]:
    block_index = -1
    open_fence: str | None = None
    cur: _Block | None = None
    for i, line in enumerate(text.splitlines(), start=1):
        if open_fence is None:
            m = _FENCE_RE.match(line)
            if m:
                fence = m.group("fence")
                info = m.group("info").strip()
                lang = info.split()[0].lower() if info else ""
                block_index += 1
                open_fence = fence[0] * len(fence)
                cur = _Block(index=block_index, start_line=i, info=info, lang=lang)
        else:
            stripped = line.lstrip(" ")
            if stripped.startswith(open_fence[0]) and re.match(rf"{re.escape(open_fence[0])}{{{len(open_fence)},}}\s*$", stripped):
                yield cur  # type: ignore[misc]
                open_fence = None
                cur = None
            else:
                cur.lines.append((i, line))  # type: ignore[union-attr]
    if cur is not None:
        # Unterminated block -- still emit it so the operator sees what was scanned.
        yield cur


def _classify_indent(line: str) -> str:
    """Return 'tab', 'space', 'mixed', or 'none' for the indent of ``line``."""
    j = 0
    saw_tab = False
    saw_space = False
    while j < len(line) and line[j] in (" ", "\t"):
        if line[j] == "\t":
            saw_tab = True
        else:
            saw_space = True
        j += 1
    if saw_tab and saw_space:
        return "mixed"
    if saw_tab:
        return "tab"
    if saw_space:
        return "space"
    return "none"


def detect_indent_mix(text: str) -> list[Finding]:
    findings: list[Finding] = []
    block_regimes: dict[int, str] = {}  # block_index -> 'tab' | 'space' | 'mixed' | 'empty'
    block_meta: dict[int, _Block] = {}

    for block in _iter_blocks(text):
        block_meta[block.index] = block
        if block.lang in _TAB_REQUIRED_LANGS:
            block_regimes[block.index] = "skipped"
            continue

        had_tab = False
        had_space = False
        had_mixed_line = False

        for line_no, raw in block.lines:
            cls = _classify_indent(raw)
            if cls == "mixed":
                had_mixed_line = True
                # Render the offending leading run so the report is actionable.
                lead = ""
                for ch in raw:
                    if ch in (" ", "\t"):
                        lead += "TAB" if ch == "\t" else "SP"
                    else:
                        break
                findings.append(Finding(
                    kind="mixed_in_line",
                    block_index=block.index,
                    block_start_line=block.start_line,
                    line_no=line_no,
                    detail=f"indent run = {lead}",
                    info_string=block.info,
                ))
            elif cls == "tab":
                had_tab = True
            elif cls == "space":
                had_space = True

        if had_tab and had_space:
            findings.append(Finding(
                kind="mixed_in_block",
                block_index=block.index,
                block_start_line=block.start_line,
                line_no=0,
                detail="block contains both tab-indented and space-indented lines",
                info_string=block.info,
            ))
            block_regimes[block.index] = "mixed"
        elif had_tab:
            block_regimes[block.index] = "tab"
        elif had_space:
            block_regimes[block.index] = "space"
        elif had_mixed_line:
            block_regimes[block.index] = "mixed"
        else:
            block_regimes[block.index] = "empty"

    pure = {idx: r for idx, r in block_regimes.items() if r in ("tab", "space")}
    regimes_present = set(pure.values())
    if len(regimes_present) > 1:
        # Doc-level finding: pin it to the second-encountered odd-one-out
        # so the operator has a single line number to jump to.
        first_regime = next(iter(pure.values()))
        for idx, r in pure.items():
            if r != first_regime:
                blk = block_meta[idx]
                findings.append(Finding(
                    kind="inconsistent_in_doc",
                    block_index=idx,
                    block_start_line=blk.start_line,
                    line_no=blk.start_line,
                    detail=f"this block is {r}-indented; earlier block(s) used {first_regime}",
                    info_string=blk.info,
                ))
                break

    findings.sort(key=lambda f: (f.block_start_line, f.line_no, f.kind))
    return findings


def format_report(findings: list[Finding]) -> str:
    if not findings:
        return "OK: no indent-mix findings."
    out = [f"FOUND {len(findings)} indent-mix finding(s):"]
    for f in findings:
        info = f" info={f.info_string!r}" if f.info_string else ""
        if f.line_no == 0:
            out.append(f"  block #{f.block_index} at line {f.block_start_line}{info}: {f.kind} -- {f.detail}")
        else:
            out.append(f"  block #{f.block_index} (opens line {f.block_start_line}) line {f.line_no}{info}: {f.kind} -- {f.detail}")
    return "\n".join(out)
