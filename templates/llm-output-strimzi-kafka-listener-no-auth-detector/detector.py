#!/usr/bin/env python3
"""Detect Strimzi ``Kafka`` custom-resource manifests where an external
or non-internal listener is declared without an ``authentication``
block.

A Strimzi listener entry under ``spec.kafka.listeners`` looks like::

    - name: external
      port: 9094
      type: route
      tls: true
      authentication:
        type: scram-sha-512

If the ``authentication`` field is omitted on a listener of ``type``
``route`` / ``loadbalancer`` / ``nodeport`` / ``ingress``, the broker
accepts unauthenticated connections from anywhere the listener is
exposed. The detector flags this shape.

Exit code is the count of files with at least one finding (capped at
255). Stdout lines have the form ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*strimzi-listener-noauth-allowed")

EXPOSED_TYPES = {"route", "loadbalancer", "nodeport", "ingress"}
INTERNAL_TYPES = {"internal", "cluster-ip"}


def _indent(line: str) -> int:
    n = 0
    for ch in line:
        if ch == " ":
            n += 1
        else:
            break
    return n


def _is_kafka_kind(source: str) -> bool:
    # crude multi-doc support
    return bool(re.search(r"^kind:\s*Kafka\b", source, re.MULTILINE))


def _find_listeners_blocks(lines: List[str]) -> List[Tuple[int, int, int]]:
    """Return list of (start_line_idx, end_line_idx_exclusive, item_indent)
    for each ``listeners:`` block under ``spec.kafka``.

    We do a structural scan: we locate any line matching ``listeners:``
    (possibly empty value) whose nearest non-deeper ancestor key is
    ``kafka:`` whose ancestor is ``spec:``.
    """
    blocks: List[Tuple[int, int, int]] = []
    # Track indent stack of mapping keys.
    key_stack: List[Tuple[int, str]] = []  # (indent, key)

    for i, raw in enumerate(lines):
        stripped = raw.split("#", 1)[0].rstrip()
        if not stripped.strip():
            continue
        ind = _indent(raw)
        # Pop stack to current indent
        while key_stack and key_stack[-1][0] >= ind:
            key_stack.pop()

        m = re.match(r"^(\s*)([A-Za-z_][\w-]*)\s*:\s*(.*)$", raw)
        if not m:
            continue
        key = m.group(2)
        rest = m.group(3).strip()

        if key == "listeners" and rest == "":
            # ancestors should include spec -> kafka
            anc_keys = [k for _, k in key_stack]
            if "spec" in anc_keys and "kafka" in anc_keys:
                # find end of block: next line with indent <= ind
                end = len(lines)
                for j in range(i + 1, len(lines)):
                    rj = lines[j]
                    sj = rj.split("#", 1)[0].rstrip()
                    if not sj.strip():
                        continue
                    if _indent(rj) <= ind:
                        end = j
                        break
                blocks.append((i, end, ind))
                key_stack.append((ind, key))
                continue

        # Push as a key on stack for ancestor tracking. Only meaningful
        # if value is empty (i.e., a mapping header).
        if rest == "":
            key_stack.append((ind, key))

    return blocks


def _parse_list_items(
    lines: List[str], start: int, end: int, base_indent: int
) -> List[Tuple[int, int]]:
    """Return list of (item_start_line, item_end_line_exclusive)."""
    items: List[Tuple[int, int]] = []
    cur_start = -1
    item_marker_indent = -1
    for i in range(start + 1, end):
        raw = lines[i]
        stripped = raw.split("#", 1)[0].rstrip()
        if not stripped.strip():
            continue
        ind = _indent(raw)
        text = raw.lstrip()
        if text.startswith("- ") or text == "-":
            # new item
            if cur_start >= 0:
                items.append((cur_start, i))
            cur_start = i
            item_marker_indent = ind
        else:
            if cur_start < 0:
                continue
            # still part of current item if indent > item_marker_indent
            if ind <= item_marker_indent:
                items.append((cur_start, i))
                cur_start = -1
    if cur_start >= 0:
        items.append((cur_start, end))
    return items


def _item_field(lines: List[str], start: int, end: int, name: str) -> str | None:
    """Get scalar field value from a list-item block. None if missing."""
    # the first line is "- key: val" or "-" then nested
    first = lines[start]
    # detect base indent for fields = indent of first non-dash content
    # field can be at indent of 'name:' on first line, or below
    # easier: scan all lines for "<name>:" within block whose indent
    # is the item field indent (any indent > item marker).
    pat = re.compile(rf"^\s*{re.escape(name)}\s*:\s*(.*?)\s*(?:#.*)?$")
    # consider first line's "- name: val"
    m_first = re.match(rf"^(\s*)-\s+{re.escape(name)}\s*:\s*(.*?)\s*(?:#.*)?$", first)
    if m_first:
        return m_first.group(2)
    for i in range(start, end):
        m = pat.match(lines[i])
        if m:
            return m.group(1)
    return None


def _item_has_block(lines: List[str], start: int, end: int, name: str) -> bool:
    pat_block = re.compile(rf"^\s*{re.escape(name)}\s*:\s*(?:#.*)?$")
    pat_inline = re.compile(rf"^\s*{re.escape(name)}\s*:\s*\S")
    # also consider on the dash line: "- authentication:"
    pat_dash_block = re.compile(rf"^\s*-\s+{re.escape(name)}\s*:\s*(?:#.*)?$")
    for i in range(start, end):
        if pat_block.match(lines[i]) or pat_inline.match(lines[i]) or pat_dash_block.match(lines[i]):
            return True
    return False


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings
    if not _is_kafka_kind(source):
        return findings

    lines = source.splitlines()
    blocks = _find_listeners_blocks(lines)
    for start, end, base_ind in blocks:
        items = _parse_list_items(lines, start, end, base_ind)
        for s, e in items:
            ltype = _item_field(lines, s, e, "type")
            lname = _item_field(lines, s, e, "name") or "<unnamed>"
            if ltype is None:
                continue
            ltype_l = ltype.strip().strip('"').strip("'").lower()
            if ltype_l in INTERNAL_TYPES:
                continue
            if ltype_l not in EXPOSED_TYPES:
                continue
            if _item_has_block(lines, s, e, "authentication"):
                continue
            findings.append((
                s + 1,
                (
                    f"Strimzi Kafka listener name={lname} type={ltype_l} "
                    "is exposed externally with no authentication block"
                ),
            ))
    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("*.yml", "*.yaml"):
                targets.extend(sorted(path.rglob(ext)))
        else:
            targets.append(path)
    seen = set()
    for f in targets:
        if f in seen:
            continue
        seen.add(f)
        try:
            source = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{f}:0:read-error: {exc}")
            continue
        hits = scan(source)
        if hits:
            bad_files += 1
            for line, reason in hits:
                print(f"{f}:{line}:{reason}")
    return bad_files


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 0
    paths = [Path(a) for a in argv[1:]]
    return min(255, scan_paths(paths))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
