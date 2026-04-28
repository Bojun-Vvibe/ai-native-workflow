#!/usr/bin/env python3
"""llm-output-yaml-duplicate-key-detector.

Pure-stdlib, code-fence-aware detector for YAML blocks emitted by an
LLM that contain duplicate mapping keys at the same nesting level.

Why it matters
--------------
The YAML 1.2 spec says duplicate keys in the same mapping are an
error, but most real-world parsers (PyYAML's `safe_load`, Go's
`gopkg.in/yaml.v2`, Ruby `Psych`) silently keep the *last* value and
discard the rest. When an LLM is asked to "merge two configs" or
"add a new env var to this Helm values file," it routinely produces:

    env:
      LOG_LEVEL: info
      DB_URL: postgres://...
      LOG_LEVEL: debug          # <-- duplicate, silently overrides

The user reads the diff, sees `LOG_LEVEL: info` near the top, and
ships a config where `LOG_LEVEL` is actually `debug` (or vice
versa). Same failure mode hits Kubernetes manifests (`env:` lists),
GitHub Actions workflows (`env:`, `with:` blocks), Ansible vars,
Docker Compose service definitions, and `pre-commit` hook configs.

This detector deliberately avoids importing PyYAML — it must work in
the stdlib-only sandbox and it must report duplicates that PyYAML
would silently swallow. So we do a lightweight scan: for each
fenced YAML block, walk lines, track the indentation stack, and on
any line of the form `<indent><key>:` (with optional value), check
whether `<key>` has already appeared at that indent within the
current parent mapping.

Usage
-----
    python3 detect.py <markdown_file>

Reads the markdown file, finds fenced code blocks whose info-string
first token (case-insensitive) is one of {yaml, yml}, and runs the
duplicate-key scan on each.

Output: one finding per duplicate on stdout::

    block=<N> line=<L> key=<k> first_seen_line=<L0> indent=<I>

Trailing summary `total_findings=<N> blocks_checked=<M>` is printed
to stderr. Exit code 0 if no findings, 1 if any.

What is in scope
----------------
    * Block-style mappings (the dominant style in config files).
    * Nested mappings — duplicates are scoped to their parent.
    * Sequence items that are themselves mappings (`- key: value`
      followed by `  key: value`); each `- ` opens a fresh mapping.

What is out of scope (deliberately)
-----------------------------------
    * Flow-style mappings (`{a: 1, a: 2}`) — rare in hand-edited
      config; would require a real tokenizer.
    * Anchors / aliases / merge keys (`<<:`).
    * Multi-document streams (`---`) — we treat each `---` as a
      hard reset of the indent stack.
    * Quoted keys with embedded colons.

These omissions are documented so reviewers know what *isn't*
caught; this is a first-line sniff test, not a YAML 1.2 conformance
checker.
"""
from __future__ import annotations

import re
import sys
from typing import Dict, List, Tuple


_YAML_TAGS = {"yaml", "yml"}

# Match `<indent><key>:` optionally followed by a space + value.
# Key can be unquoted (no colon, no `#`, no leading `-`/`?`/`*`/`&`),
# single-quoted, or double-quoted. We do NOT try to handle quoted
# keys containing escapes — rare in config files.
_KEY_LINE = re.compile(
    r"""^
    (?P<indent>[ ]*)                      # leading spaces only (no tabs in spec)
    (?:-[ ]+)?                            # optional sequence dash + space
    (?P<key>
        "(?:[^"\\]|\\.)*"                 # double-quoted
      | '(?:[^'\\]|\\.)*'                 # single-quoted
      | [^\s\#\-\?\*\&\!\|\>\{\[\"\'][^:\#]*?
                                          # unquoted: must not start with
                                          # YAML structural chars
    )
    [ ]*:                                 # the colon
    (?:[ \t]|$)                           # then space/tab/EOL
    """,
    re.VERBOSE,
)


def extract_yaml_blocks(src: str) -> List[Tuple[int, int, str]]:
    """Return list of (block_idx, start_line_no, body) for each YAML block.

    start_line_no is the 1-indexed line of the first line *inside*
    the fence.
    """
    blocks: List[Tuple[int, int, str]] = []
    lines = src.splitlines()
    i = 0
    in_fence = False
    fence_char = ""
    fence_len = 0
    fence_tag = ""
    body: List[str] = []
    body_start = 0
    block_idx = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if not in_fence:
            if stripped.startswith("```") or stripped.startswith("~~~"):
                ch = stripped[0]
                run = len(stripped) - len(stripped.lstrip(ch))
                if run >= 3:
                    info = stripped[run:].strip()
                    tag = info.split()[0].lower() if info else ""
                    in_fence = True
                    fence_char = ch
                    fence_len = run
                    fence_tag = tag
                    body = []
                    body_start = i + 2  # 1-indexed line *inside* fence
        else:
            if stripped.startswith(fence_char * fence_len) and \
                    set(stripped) <= {fence_char, " ", "\t"}:
                if fence_tag in _YAML_TAGS:
                    block_idx += 1
                    blocks.append((block_idx, body_start, "\n".join(body)))
                in_fence = False
                fence_char = ""
                fence_len = 0
                fence_tag = ""
                body = []
            else:
                body.append(line)
        i += 1

    # Unterminated fence: still scan if it was tagged YAML.
    if in_fence and fence_tag in _YAML_TAGS:
        block_idx += 1
        blocks.append((block_idx, body_start, "\n".join(body)))

    return blocks


def _normalize_key(raw: str) -> str:
    """Strip surrounding quotes from a key, leaving inner content as-is."""
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        return raw[1:-1]
    return raw.rstrip()


def find_duplicates(body: str, body_start: int) -> List[Tuple[int, str, int, int]]:
    """Scan a YAML body for duplicate keys.

    Returns list of (line_no, key, first_seen_line_no, indent).
    """
    findings: List[Tuple[int, str, int, int]] = []
    # Stack of (indent, {key: first_line_no}) frames. The top of the
    # stack is the currently-open mapping.
    stack: List[Tuple[int, Dict[str, int]]] = [(-1, {})]

    for offset, raw in enumerate(body.split("\n")):
        line_no = body_start + offset
        # Skip blank, pure-comment, and document-marker lines.
        s = raw.rstrip()
        if not s or s.lstrip().startswith("#"):
            continue
        if s.strip() in ("---", "..."):
            stack = [(-1, {})]
            continue

        m = _KEY_LINE.match(raw)
        if not m:
            # Not a key line (could be a scalar continuation, a
            # bare sequence item `- value`, etc.). Don't touch
            # the stack — its indent gates handle popping.
            continue

        indent = len(m.group("indent"))
        # If the line has a leading `- `, the key effectively lives
        # at `indent + 2` (the dash + space themselves count as
        # indentation for the inner mapping).
        leading = raw[indent : indent + 2]
        if leading == "- ":
            # `- key:` opens a *new* mapping inside a sequence.
            # The new mapping's effective indent is indent + 2.
            # Each `- ` always opens a fresh scope, even if a frame
            # at that indent already exists from a prior list item.
            inner_indent = indent + 2
            while stack and stack[-1][0] > inner_indent:
                stack.pop()
            if stack and stack[-1][0] == inner_indent:
                stack.pop()
            stack.append((inner_indent, {}))
            key = _normalize_key(m.group("key"))
            stack[-1][1][key] = line_no
            continue

        # Plain `key:` line. Pop frames whose indent is *strictly*
        # deeper than this one; reuse a frame at the same indent.
        while stack and stack[-1][0] > indent:
            stack.pop()
        if not stack or stack[-1][0] < indent:
            stack.append((indent, {}))

        key = _normalize_key(m.group("key"))
        frame_keys = stack[-1][1]
        if key in frame_keys:
            findings.append((line_no, key, frame_keys[key], indent))
        else:
            frame_keys[key] = line_no

    return findings


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("usage: detect.py <markdown_file>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as fh:
        src = fh.read()

    blocks = extract_yaml_blocks(src)
    total = 0
    for block_idx, body_start, body in blocks:
        for line_no, key, first, indent in find_duplicates(body, body_start):
            print(
                f"block={block_idx} line={line_no} key={key} "
                f"first_seen_line={first} indent={indent}"
            )
            total += 1

    print(
        f"total_findings={total} blocks_checked={len(blocks)}",
        file=sys.stderr,
    )
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
