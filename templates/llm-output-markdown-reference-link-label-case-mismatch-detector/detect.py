#!/usr/bin/env python3
"""Detect case-mismatched reference link labels in Markdown.

Usage:  python3 detect.py <markdown-file>
Exit:   0 = clean, 1 = findings, 2 = usage/IO error.
"""
from __future__ import annotations

import re
import sys

# Reference link definition: at start of line (up to 3 spaces of
# indent), `[label]: url ...` to end of line.
DEF_RE = re.compile(r"^[ ]{0,3}\[(?P<label>[^\]\n]+)\]:\s*\S+")

# Collapsed reference: `[text][label]` or shortcut `[label]` followed
# by something other than `(` and not `:` (definition). We capture
# both forms and dedupe.
FULL_REF_RE = re.compile(r"\[(?P<text>[^\[\]\n]+)\]\[(?P<label>[^\[\]\n]*)\]")
# Shortcut/collapsed form: `[label][]` or `[label]` (when nothing
# follows that would make it an inline link or definition).
SHORTCUT_RE = re.compile(r"\[(?P<label>[^\[\]\n]+)\](?!\(|\[|:)")


def normalize(label: str) -> str:
    # CommonMark: case-fold + collapse internal whitespace + trim.
    return re.sub(r"\s+", " ", label.strip()).casefold()


def find_fences(lines):
    """Return set of 0-indexed line numbers that lie inside a fenced
    code block. Used to skip references that are part of code samples."""
    inside = set()
    i = 0
    fence_re = re.compile(r"^[ ]{0,3}(?P<f>`{3,}|~{3,})")
    while i < len(lines):
        m = fence_re.match(lines[i])
        if not m:
            i += 1
            continue
        f = m.group("f")
        ch = f[0]
        n = len(f)
        j = i + 1
        close_re = re.compile(r"^[ ]{0,3}" + re.escape(ch) + r"{" + str(n) + r",}\s*$")
        while j < len(lines):
            inside.add(j)
            if close_re.match(lines[j]):
                break
            j += 1
        i = j + 1
    return inside


def scan(text: str):
    lines = text.splitlines()
    fence_lines = find_fences(lines)

    # Pass 1: collect all definitions.
    # canonical -> list of (line_1based, col_1based, raw_label)
    defs: dict[str, list[tuple[int, int, str]]] = {}
    for li, raw in enumerate(lines):
        if li in fence_lines:
            continue
        m = DEF_RE.match(raw)
        if not m:
            continue
        label = m.group("label")
        defs.setdefault(normalize(label), []).append((li + 1, raw.find("[") + 1, label))

    # Pass 2: collect all references (full + shortcut).
    # canonical -> list of (line, col, raw_label)
    refs: dict[str, list[tuple[int, int, str]]] = {}
    for li, raw in enumerate(lines):
        if li in fence_lines:
            continue
        if DEF_RE.match(raw):
            continue  # skip the definition line itself
        # Strip inline code spans to avoid false positives.
        stripped = re.sub(r"`[^`\n]*`", lambda m: " " * len(m.group(0)), raw)
        # Full references — record their character spans so the
        # shortcut pass can skip anything inside them.
        full_spans: list[tuple[int, int]] = []
        for fm in FULL_REF_RE.finditer(stripped):
            label = fm.group("label").strip() or fm.group("text")
            full_spans.append((fm.start(), fm.end()))
            if not label:
                continue
            refs.setdefault(normalize(label), []).append(
                (li + 1, fm.start() + 1, label)
            )
        # Shortcut references — only count those whose normalized
        # label is a known definition (otherwise they are just
        # bracketed prose).
        for sm in SHORTCUT_RE.finditer(stripped):
            # Skip shortcuts that are wholly inside a full reference.
            if any(s <= sm.start() and sm.end() <= e for s, e in full_spans):
                continue
            label = sm.group("label")
            canon = normalize(label)
            if canon in defs:
                refs.setdefault(canon, []).append(
                    (li + 1, sm.start() + 1, label)
                )

    findings = []

    # Finding kind 1: duplicate definitions, different casing.
    for canon, ds in defs.items():
        casings = {d[2] for d in ds}
        if len(ds) > 1 and len(casings) > 1:
            # Report each definition after the first as a finding.
            for line, col, raw_label in ds[1:]:
                findings.append(
                    (
                        line,
                        col,
                        "multiple_definitions_different_case",
                        canon,
                        ",".join(sorted(casings)),
                    )
                )

    # Finding kind 2: reference uses different casing than its definition.
    for canon, rs in refs.items():
        if canon not in defs:
            continue  # orphan; covered by a different template
        def_casings = {d[2] for d in defs[canon]}
        for line, col, raw_label in rs:
            if raw_label not in def_casings:
                all_forms = sorted(def_casings | {raw_label})
                findings.append(
                    (
                        line,
                        col,
                        "reference_case_mismatch_with_definition",
                        canon,
                        ",".join(all_forms),
                    )
                )

    findings.sort(key=lambda t: (t[0], t[1], t[2]))
    return findings


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: detect.py <markdown-file>\n")
        return 2
    try:
        with open(argv[1], "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write(f"io error: {e}\n")
        return 2
    findings = scan(text)
    for line, col, kind, canon, forms in findings:
        print(f"{line}:{col} {kind} label={canon} forms={forms}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
