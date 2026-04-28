"""llm-output-yaml-indentation-mix-detector — checker + worked demo.

Pure-stdlib detector for indentation hazards inside YAML blocks emitted
by an LLM. YAML is whitespace-significant: a single tab in an
otherwise-space-indented block, or a sibling indent that jumps from
2-space to 4-space, can flip the document's tree shape without raising
a syntax error in every parser. PyYAML rejects tabs outright; some
strict CI parsers reject mixed indent steps; many "tolerant" parsers
silently re-shape the tree. The model never sees which parser the
downstream consumer uses.

This detector scans markdown emitted by an LLM, locates fenced code
blocks whose info string identifies them as YAML (``` yaml / ``` yml /
``` YAML), and inspects only the lines inside those fences. Anything
outside a yaml fence is ignored — we are not a YAML parser, we are a
hazard sniffer for *YAML embedded in LLM markdown output*.

What it catches per yaml block:

  * tab_in_indent       — a TAB character appears in the leading
                          whitespace of a non-blank, non-comment line
  * mixed_indent_step   — sibling lines at the same logical level use
                          different indent widths (e.g. one nests at
                          +2 spaces, the next at +4)
  * indent_step_zero    — a child line is indented the same as its
                          parent (zero net indent for a nested key)
  * cr_line_ending      — a CR byte appears at end-of-line inside the
                          yaml block (CRLF or bare-CR), which trips
                          some strict YAML parsers

Design notes:

  * Code-fence-aware. Only content inside ```yaml / ```yml fences
    is inspected. The rest of the markdown is skipped.
  * Comment-aware. Lines whose first non-whitespace char is `#` are
    not used as evidence for indent-step decisions but ARE checked
    for tab leakage.
  * Document-separator-aware. `---` and `...` reset the indent stack
    inside a yaml block.
  * Block-scalar-aware. After a key ending in `|`, `>`, `|-`, `>+`,
    etc., the indented body is treated as opaque text and not
    inspected for indent-step consistency (its indent is its content).
    Tabs in that body are still flagged.
  * Pure function. `detect(src) -> YamlIndentReport`. No I/O.
  * Stdlib only. dataclasses + json (for serialising the report) + sys.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class Finding:
    kind: str
    line_no: int       # 1-indexed line in the original source
    col_no: int        # 1-indexed column where the hazard starts
    detail: str


@dataclass
class YamlIndentReport:
    ok: bool
    yaml_blocks_checked: int
    yaml_lines_checked: int
    findings: List[Finding] = field(default_factory=list)


_BLOCK_SCALAR_INDICATORS = ("|", ">", "|-", ">-", "|+", ">+")


def _is_yaml_fence_open(line: str) -> bool:
    """Return True if `line` opens a fenced code block tagged as yaml."""
    s = line.lstrip()
    if not (s.startswith("```") or s.startswith("~~~")):
        return False
    # strip the fence chars themselves
    if s.startswith("```"):
        info = s[3:].strip()
    else:
        info = s[3:].strip()
    if not info:
        return False
    # info string may be `yaml`, `yml`, `YAML`, or `yaml something`
    first = info.split()[0].lower().strip(",")
    return first in ("yaml", "yml")


def _is_fence_close(line: str) -> bool:
    s = line.strip()
    return s == "```" or s == "~~~"


def _leading_ws(line: str) -> str:
    j = 0
    while j < len(line) and line[j] in (" ", "\t"):
        j += 1
    return line[:j]


def _indent_width(ws: str) -> int:
    """Treat tabs as 1 column for hazard detection (we flag them
    separately). The width is just the count of whitespace chars."""
    return len(ws)


def _ends_block_scalar(content: str) -> bool:
    """Detect whether a yaml mapping value introduces a block scalar."""
    # strip trailing comment
    hash_pos = -1
    in_squote = False
    in_dquote = False
    for i, c in enumerate(content):
        if c == "'" and not in_dquote:
            in_squote = not in_squote
        elif c == '"' and not in_squote:
            in_dquote = not in_dquote
        elif c == "#" and not in_squote and not in_dquote:
            # `#` must be preceded by whitespace to be a comment
            if i == 0 or content[i - 1] in (" ", "\t"):
                hash_pos = i
                break
    body = content if hash_pos < 0 else content[:hash_pos]
    body = body.rstrip()
    for ind in _BLOCK_SCALAR_INDICATORS:
        if body.endswith(": " + ind) or body.endswith(":" + ind):
            return True
        # also bare "|" after a sequence dash, e.g. "- |"
        if body.endswith("- " + ind) or body == ind or body.endswith(" " + ind):
            return True
    return False


def detect(src: str) -> YamlIndentReport:
    findings: List[Finding] = []
    yaml_blocks = 0
    yaml_lines = 0

    lines = src.splitlines(keepends=True)
    in_yaml = False
    # indent stack of active levels seen so far in this yaml block
    indent_levels: List[int] = []
    # if > 0, we are inside a block scalar body and must skip indent-step checks
    block_scalar_min_indent: Optional[int] = None

    for idx, raw in enumerate(lines):
        # detect CRLF / bare CR inside the line content
        line_no = idx + 1
        line_no_crlf_strip = raw
        had_cr = False
        if line_no_crlf_strip.endswith("\r\n"):
            had_cr = True
            line = line_no_crlf_strip[:-2]
        elif line_no_crlf_strip.endswith("\n"):
            line = line_no_crlf_strip[:-1]
            if line.endswith("\r"):
                had_cr = True
                line = line[:-1]
        else:
            line = line_no_crlf_strip
            if line.endswith("\r"):
                had_cr = True
                line = line[:-1]

        if not in_yaml:
            if _is_yaml_fence_open(line):
                in_yaml = True
                yaml_blocks += 1
                indent_levels = []
                block_scalar_min_indent = None
            continue

        # in_yaml == True
        if _is_fence_close(line):
            in_yaml = False
            indent_levels = []
            block_scalar_min_indent = None
            continue

        yaml_lines += 1

        if had_cr:
            findings.append(Finding(
                kind="cr_line_ending",
                line_no=line_no,
                col_no=len(line) + 1,
                detail="CR byte at end of line inside yaml block; "
                       "strict YAML parsers reject CRLF / bare-CR",
            ))

        ws = _leading_ws(line)
        rest = line[len(ws):]

        # tab in indent — always a finding, even on comment / blank lines
        if "\t" in ws:
            tab_col = ws.index("\t") + 1
            findings.append(Finding(
                kind="tab_in_indent",
                line_no=line_no,
                col_no=tab_col,
                detail="TAB character in leading whitespace; PyYAML and "
                       "strict parsers reject this outright",
            ))

        # blank lines do not affect indent stack
        if rest.strip() == "":
            continue

        # `---` / `...` reset the indent stack
        stripped = rest.strip()
        if stripped == "---" or stripped == "...":
            indent_levels = []
            block_scalar_min_indent = None
            continue

        # comment lines — checked for tabs above, but skip indent logic
        if rest.lstrip().startswith("#"):
            continue

        width = _indent_width(ws)

        # if we are inside a block scalar body, skip indent-step checks
        # until we exit the body (line dedented to <= scalar parent)
        if block_scalar_min_indent is not None:
            if width >= block_scalar_min_indent:
                # still in body — opaque
                continue
            # exited body
            block_scalar_min_indent = None

        # pop levels deeper than this line
        while indent_levels and indent_levels[-1] > width:
            indent_levels.pop()

        if not indent_levels:
            indent_levels.append(width)
        elif indent_levels[-1] == width:
            pass  # sibling at same level
        else:
            # new deeper level
            parent_width = indent_levels[-1]
            step = width - parent_width
            if step <= 0:
                # should not happen because we popped above, but be defensive
                findings.append(Finding(
                    kind="indent_step_zero",
                    line_no=line_no,
                    col_no=1,
                    detail="child line indented the same or less than its "
                           "parent in the indent stack",
                ))
            else:
                # check against existing step deltas in the stack
                # compute prior step (between top and the level below it)
                if len(indent_levels) >= 2:
                    prior_step = indent_levels[-1] - indent_levels[-2]
                    if prior_step != step:
                        findings.append(Finding(
                            kind="mixed_indent_step",
                            line_no=line_no,
                            col_no=parent_width + 1,
                            detail=(
                                "indent step changed from "
                                f"{prior_step} to {step} spaces between "
                                "sibling nesting levels in the same yaml "
                                "block"
                            ),
                        ))
                indent_levels.append(width)

        # detect block-scalar introduction so we skip its body
        if _ends_block_scalar(rest):
            block_scalar_min_indent = width + 1

    findings.sort(key=lambda f: (f.line_no, f.col_no, f.kind))
    return YamlIndentReport(
        ok=len(findings) == 0,
        yaml_blocks_checked=yaml_blocks,
        yaml_lines_checked=yaml_lines,
        findings=findings,
    )


def report_to_json(rep: YamlIndentReport) -> str:
    return json.dumps(
        {
            "ok": rep.ok,
            "yaml_blocks_checked": rep.yaml_blocks_checked,
            "yaml_lines_checked": rep.yaml_lines_checked,
            "findings": [asdict(f) for f in rep.findings],
        },
        indent=2,
        sort_keys=True,
    )


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(
            "usage: detector.py <markdown-file> [<markdown-file> ...]",
            file=sys.stderr,
        )
        return 2
    overall_ok = True
    for path in argv[1:]:
        rep = detect(_read(path))
        print(f"=== {path} ===")
        print(report_to_json(rep))
        if not rep.ok:
            overall_ok = False
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
