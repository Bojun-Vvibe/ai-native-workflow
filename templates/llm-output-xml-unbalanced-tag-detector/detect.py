#!/usr/bin/env python3
"""llm-output-xml-unbalanced-tag-detector.

Pure-stdlib, code-fence-aware detector for *unbalanced XML/HTML tags*
in fenced blocks emitted by an LLM inside a markdown document.

LLMs frequently emit XML/HTML/SVG fragments with one of these defects:

  * an opening tag with no matching close (`<config>...EOF`)
  * a close tag for a tag that was never opened (`...</config>`)
  * a close tag whose name does not match the most recent open tag
    (`<a><b></a></b>` — crossed nesting)

The model has no parser in its loop, so it cannot see the imbalance.
Downstream XML parsers raise; downstream HTML parsers silently
auto-close, producing a tree that diverges from what the model
intended. This detector flags the imbalance at emit time.

Usage
-----
    python3 detect.py <markdown_file>

Reads the markdown file, finds fenced code blocks whose info-string
first token (case-insensitive) is one of {xml, html, svg, xhtml, rss,
atom, plist}, and runs the balance check on each.

Output: one finding per line on stdout, of the form:
    block=<N> line=<L> kind=<unmatched_open|unexpected_close|crossed_close> tag=<t> [open_line=<L0>]

Trailing summary `total_findings=<N> blocks_checked=<M>` on stderr.
Exit code 0 if no findings, 1 if any.

What it flags
-------------
    unmatched_open      <foo> opened, never closed before block end.
    unexpected_close    </foo> appeared without a matching open.
    crossed_close       </foo> appeared but the most recent open is <bar>.

Self-closing tags (`<br/>`, `<img/>`) are ignored. XML declarations
(`<?xml ?>`), processing instructions (`<?...?>`), comments
(`<!--...-->`), and CDATA sections (`<![CDATA[...]]>`) are skipped.
HTML void elements (`br`, `hr`, `img`, `input`, `meta`, `link`,
`area`, `base`, `col`, `embed`, `source`, `track`, `wbr`) are also
treated as self-closing so plain HTML doesn't drown the output.

Out of scope (deliberately): full XML well-formedness, attribute
quoting, entity correctness, namespace prefix balance. A grammar
checker is somebody else's template.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class Finding:
    block_idx: int
    line_no: int
    kind: str
    tag: str
    open_line: int  # -1 when not applicable


_XML_TAGS = {"xml", "html", "svg", "xhtml", "rss", "atom", "plist"}

_HTML_VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


def extract_xml_blocks(src: str) -> List[Tuple[int, int, str]]:
    """Return list of (block_idx, start_line_no, body) per XML/HTML block."""
    blocks: List[Tuple[int, int, str]] = []
    lines = src.splitlines()
    i = 0
    in_fence = False
    fence_char = ""
    fence_len = 0
    fence_tag = ""
    body: List[str] = []
    block_idx = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if not in_fence:
            if stripped.startswith("```") or stripped.startswith("~~~"):
                ch = stripped[0]
                run = 0
                while run < len(stripped) and stripped[run] == ch:
                    run += 1
                if run >= 3:
                    info = stripped[run:].strip()
                    tag = info.split()[0].lower() if info else ""
                    in_fence = True
                    fence_char = ch
                    fence_len = run
                    fence_tag = tag
                    body = []
                    i += 1
                    continue
            i += 1
            continue
        # in_fence
        if stripped.startswith(fence_char * fence_len) and set(stripped.rstrip()) <= {fence_char}:
            if fence_tag in _XML_TAGS:
                block_idx += 1
                blocks.append((block_idx, 0, "\n".join(body)))
            in_fence = False
            fence_tag = ""
            i += 1
            continue
        body.append(line)
        i += 1
    if in_fence and fence_tag in _XML_TAGS:
        block_idx += 1
        blocks.append((block_idx, 0, "\n".join(body)))
    return blocks


def _strip_special_regions(body: str) -> str:
    """Remove comments, CDATA, processing instructions, doctypes — keep
    line count stable by replacing them with spaces+newlines."""
    out = []
    i = 0
    n = len(body)
    while i < n:
        if body.startswith("<!--", i):
            end = body.find("-->", i + 4)
            if end < 0:
                # eat rest as comment, preserving newlines
                for ch in body[i:]:
                    out.append("\n" if ch == "\n" else " ")
                return "".join(out)
            for ch in body[i:end + 3]:
                out.append("\n" if ch == "\n" else " ")
            i = end + 3
            continue
        if body.startswith("<![CDATA[", i):
            end = body.find("]]>", i + 9)
            if end < 0:
                for ch in body[i:]:
                    out.append("\n" if ch == "\n" else " ")
                return "".join(out)
            for ch in body[i:end + 3]:
                out.append("\n" if ch == "\n" else " ")
            i = end + 3
            continue
        if body.startswith("<?", i):
            end = body.find("?>", i + 2)
            if end < 0:
                for ch in body[i:]:
                    out.append("\n" if ch == "\n" else " ")
                return "".join(out)
            for ch in body[i:end + 2]:
                out.append("\n" if ch == "\n" else " ")
            i = end + 2
            continue
        if body.startswith("<!", i):
            # DOCTYPE etc. — strip to next '>'
            end = body.find(">", i + 2)
            if end < 0:
                for ch in body[i:]:
                    out.append("\n" if ch == "\n" else " ")
                return "".join(out)
            for ch in body[i:end + 1]:
                out.append("\n" if ch == "\n" else " ")
            i = end + 1
            continue
        out.append(body[i])
        i += 1
    return "".join(out)


def _iter_tags(body: str):
    """Yield (line_no, kind, name) where kind in {open, close, self}.

    Skips malformed `<` (e.g. `<3` numeric comparison in code samples).
    """
    n = len(body)
    i = 0
    line_no = 1
    while i < n:
        ch = body[i]
        if ch == "\n":
            line_no += 1
            i += 1
            continue
        if ch != "<":
            i += 1
            continue
        # find matching '>'
        end = body.find(">", i + 1)
        if end < 0:
            return
        inner = body[i + 1:end]
        if not inner or inner[0].isspace():
            # advance past '<' only — the '>' may belong elsewhere
            i += 1
            continue
        is_close = inner.startswith("/")
        is_self = inner.endswith("/") and not is_close
        name_src = inner[1:] if is_close else inner
        if is_self:
            name_src = name_src[:-1]
        # tag name = up to first whitespace or '/'
        name = ""
        for c in name_src:
            if c.isspace() or c == "/":
                break
            name += c
        if not name or not (name[0].isalpha() or name[0] == "_"):
            # not a tag (e.g. `<3`); skip just the '<'
            i += 1
            continue
        kind = "close" if is_close else ("self" if is_self else "open")
        yield (line_no, kind, name)
        # advance line counter by newlines in the consumed region
        consumed = body[i:end + 1]
        line_no += consumed.count("\n")
        i = end + 1


def detect_in_block(body: str) -> List[Tuple[int, str, str, int]]:
    """Return list of (line_no, kind, tag, open_line) findings in one XML block."""
    cleaned = _strip_special_regions(body)
    findings: List[Tuple[int, str, str, int]] = []
    stack: List[Tuple[str, int]] = []  # (name, line_no)
    for line_no, kind, name in _iter_tags(cleaned):
        if kind == "self":
            continue
        if kind == "open":
            if name.lower() in _HTML_VOID:
                continue
            stack.append((name, line_no))
            continue
        # kind == "close"
        if name.lower() in _HTML_VOID:
            # explicit close of a void element — ignore (HTML allows)
            continue
        if not stack:
            findings.append((line_no, "unexpected_close", name, -1))
            continue
        top_name, top_line = stack[-1]
        if top_name == name:
            stack.pop()
            continue
        # crossed close — try to find a matching open further down the stack
        match_idx = None
        for k in range(len(stack) - 1, -1, -1):
            if stack[k][0] == name:
                match_idx = k
                break
        if match_idx is None:
            findings.append((line_no, "unexpected_close", name, -1))
        else:
            findings.append((line_no, "crossed_close", name, stack[match_idx][1]))
            # pop everything down to and including the matched open so
            # subsequent imbalance reports stay sensible
            del stack[match_idx:]
    for name, open_line in stack:
        findings.append((open_line, "unmatched_open", name, -1))
    findings.sort(key=lambda f: (f[0], f[2], f[1]))
    return findings


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("usage: detect.py <markdown_file>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as fh:
        src = fh.read()
    blocks = extract_xml_blocks(src)
    total = 0
    for block_idx, _start, body in blocks:
        for line_no, kind, tag, open_line in detect_in_block(body):
            total += 1
            extra = f" open_line={open_line}" if open_line >= 0 else ""
            print(f"block={block_idx} line={line_no} kind={kind} tag={tag}{extra}")
    print(f"total_findings={total} blocks_checked={len(blocks)}", file=sys.stderr)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
