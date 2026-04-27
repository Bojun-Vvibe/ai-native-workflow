"""llm-output-markdown-yaml-frontmatter-validator

Pure stdlib detector that scans a markdown document produced by an
LLM for malformed YAML frontmatter blocks. The failure modes it
catches:

  - `missing_open`        : doc starts with `...` (close marker)
                            without a prior `---` opener.
  - `missing_close`       : doc opens with `---` on line 1 but no
                            closing `---` / `...` line is found.
  - `not_at_top`          : a `---` block appears later in the doc
                            and *looks* like frontmatter; static
                            site generators only honour frontmatter
                            on line 1.
  - `empty_block`         : the frontmatter delimiters are present
                            but the body between them is empty
                            (whitespace only). Some renderers treat
                            this as a horizontal rule instead.
  - `tab_indent`          : a body line uses a tab for indentation;
                            YAML 1.2 forbids tabs as indent and
                            many parsers reject the file.
  - `duplicate_key`       : a top-level key appears twice. YAML
                            allows it, but downstream consumers
                            (Hugo, Jekyll, Eleventy, MkDocs, our
                            own RAG indexers) silently use only one
                            and the choice differs across tools.
  - `unquoted_special`    : a top-level scalar value starts with a
                            character that needs quoting in YAML
                            (`@`, `` ` ``, `%`, `&`, `*`, `!`, `|`,
                            `>`, `?`, `:` followed by space) and
                            is not quoted.
  - `missing_colon_space` : a body line that looks like a key/value
                            pair uses `key:value` (no space after
                            the colon). YAML requires `key: value`
                            for plain scalars.
  - `bom_in_block`        : a UTF-8 BOM appears inside the
                            frontmatter body (almost always means
                            the doc was concatenated from two
                            sources).

Stdlib only. Pure function over a string. Findings sorted by
`(kind, line_no, detail)` so two runs produce byte-identical
output (cron-friendly diffing). No `yaml` import — we deliberately
avoid PyYAML because the goal is to catch problems *before* they
reach a real parser, and because PyYAML accepts inputs that Hugo
and Jekyll reject.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple


class FrontmatterValidationError(ValueError):
    """Raised eagerly on bad input type."""


@dataclass(frozen=True)
class Finding:
    kind: str
    line_no: int
    detail: str


@dataclass
class FrontmatterReport:
    ok: bool
    has_frontmatter: bool
    open_line: Optional[int] = None
    close_line: Optional[int] = None
    keys: List[str] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "ok": self.ok,
                "has_frontmatter": self.has_frontmatter,
                "open_line": self.open_line,
                "close_line": self.close_line,
                "keys": self.keys,
                "findings": [asdict(f) for f in self.findings],
            },
            indent=2,
            sort_keys=True,
        )


_FENCE_OPEN = "---"
_FENCE_CLOSE_ALT = "..."
_BOM = "\ufeff"

# YAML scalar values starting with these chars must be quoted.
_NEED_QUOTE_FIRST = set("@`%&*!|>?")


def _looks_like_kv(line: str) -> Optional[Tuple[str, str]]:
    """Return (key, value) if the line is a plausible top-level
    YAML key/value pair, else None. Top-level means zero indent.
    """
    if not line or line[0] in " \t":
        return None
    if line.startswith("#"):
        return None
    if ":" not in line:
        return None
    # Find the first ':' that splits key from value.
    # Quoted keys are out of scope for this lightweight check.
    idx = line.find(":")
    key = line[:idx].rstrip()
    value = line[idx + 1:]
    return (key, value)


def check(text: str) -> FrontmatterReport:
    if not isinstance(text, str):
        raise FrontmatterValidationError("input must be str")

    findings: List[Finding] = []
    lines = text.splitlines()

    # Find the opener. CommonMark/Hugo/Jekyll all require the
    # frontmatter to start on line 1 with exactly "---".
    if not lines:
        return FrontmatterReport(ok=True, has_frontmatter=False)

    first = lines[0]
    if first == _FENCE_CLOSE_ALT:
        findings.append(Finding(
            kind="missing_open",
            line_no=1,
            detail="document starts with '...' but no prior '---' opener",
        ))
        # Try to recover by treating line 1 as a pseudo-opener for
        # the rest of the scan, but report has_frontmatter=False.
        findings.sort(key=lambda f: (f.kind, f.line_no, f.detail))
        return FrontmatterReport(
            ok=False,
            has_frontmatter=False,
            findings=findings,
        )

    if first != _FENCE_OPEN:
        # Look for a stray '---' block later — that's the not_at_top
        # smell. Heuristic: a "---" alone on a later line followed
        # within 20 lines by another "---" alone, with key:value
        # bodies in between.
        for i in range(1, len(lines)):
            if lines[i] != _FENCE_OPEN:
                continue
            # scan forward up to 20 lines for a closer
            for j in range(i + 1, min(i + 21, len(lines))):
                if lines[j] in (_FENCE_OPEN, _FENCE_CLOSE_ALT):
                    body = lines[i + 1:j]
                    looks_like_kv_count = sum(
                        1 for b in body if _looks_like_kv(b)
                    )
                    if looks_like_kv_count >= 1:
                        findings.append(Finding(
                            kind="not_at_top",
                            line_no=i + 1,
                            detail=(
                                "frontmatter-like '---' block at line"
                                f" {i + 1} but doc does not open with"
                                " '---' on line 1"
                            ),
                        ))
                        break
                    break
            break
        findings.sort(key=lambda f: (f.kind, f.line_no, f.detail))
        return FrontmatterReport(
            ok=(len(findings) == 0),
            has_frontmatter=False,
            findings=findings,
        )

    # We have an opener on line 1. Find the closer.
    open_line = 1
    close_line: Optional[int] = None
    for i in range(1, len(lines)):
        if lines[i] in (_FENCE_OPEN, _FENCE_CLOSE_ALT):
            close_line = i + 1  # 1-indexed
            break

    if close_line is None:
        findings.append(Finding(
            kind="missing_close",
            line_no=open_line,
            detail="frontmatter opener '---' on line 1 has no closing '---' or '...'",
        ))
        findings.sort(key=lambda f: (f.kind, f.line_no, f.detail))
        return FrontmatterReport(
            ok=False,
            has_frontmatter=True,
            open_line=open_line,
            close_line=None,
            findings=findings,
        )

    body = lines[open_line:close_line - 1]
    if not body or all(not b.strip() for b in body):
        findings.append(Finding(
            kind="empty_block",
            line_no=open_line,
            detail="frontmatter delimiters present but body is empty / whitespace-only",
        ))

    # Walk the body for finer-grained smells.
    seen_keys: Dict[str, int] = {}
    keys: List[str] = []
    for offset, raw in enumerate(body, start=2):  # body starts at line 2
        line_no = offset
        if _BOM in raw:
            findings.append(Finding(
                kind="bom_in_block",
                line_no=line_no,
                detail="UTF-8 BOM character inside frontmatter body",
            ))
        # tab indent on a continuation line
        if raw.startswith("\t") or (
            len(raw) > 1 and raw[0] == " " and "\t" in raw[: max(
                1, len(raw) - len(raw.lstrip())
            )]
        ):
            findings.append(Finding(
                kind="tab_indent",
                line_no=line_no,
                detail="YAML 1.2 forbids tab characters in indentation",
            ))
        kv = _looks_like_kv(raw)
        if kv is None:
            continue
        key, value = kv
        # missing space after colon
        if value and not value.startswith((" ", "\t")):
            findings.append(Finding(
                kind="missing_colon_space",
                line_no=line_no,
                detail=(
                    f"key {key!r} uses 'key:value' without a space"
                    " after the colon"
                ),
            ))
        # duplicate top-level key
        if key in seen_keys:
            findings.append(Finding(
                kind="duplicate_key",
                line_no=line_no,
                detail=(
                    f"top-level key {key!r} duplicates definition at"
                    f" line {seen_keys[key]}"
                ),
            ))
        else:
            seen_keys[key] = line_no
            keys.append(key)

        # unquoted special leading char in value
        v = value.lstrip(" \t")
        if v and v[0] in _NEED_QUOTE_FIRST:
            findings.append(Finding(
                kind="unquoted_special",
                line_no=line_no,
                detail=(
                    f"value for {key!r} starts with {v[0]!r} which"
                    " must be quoted in YAML"
                ),
            ))

    findings.sort(key=lambda f: (f.kind, f.line_no, f.detail))
    return FrontmatterReport(
        ok=(len(findings) == 0),
        has_frontmatter=True,
        open_line=open_line,
        close_line=close_line,
        keys=keys,
        findings=findings,
    )


# ---------------------------------------------------------------- demo

_CASES: List[Tuple[str, str]] = [
    (
        "01_clean",
        "---\n"
        "title: Hello World\n"
        "date: 2026-04-27\n"
        "tags:\n"
        "  - python\n"
        "  - markdown\n"
        "---\n"
        "\n"
        "# Body\n",
    ),
    (
        "02_no_frontmatter_clean",
        "# Just a Document\n\nNo frontmatter here.\n",
    ),
    (
        "03_missing_close",
        "---\n"
        "title: Broken\n"
        "date: 2026-04-27\n"
        "\n"
        "# Body that is silently part of the YAML\n",
    ),
    (
        "04_missing_open",
        "...\n"
        "title: Stray\n"
        "# Body\n",
    ),
    (
        "05_not_at_top",
        "# Heading first\n\n"
        "Some intro paragraph.\n\n"
        "---\n"
        "title: Looks like frontmatter\n"
        "author: Someone\n"
        "---\n\n"
        "More body.\n",
    ),
    (
        "06_empty_block",
        "---\n"
        "---\n"
        "# Body\n",
    ),
    (
        "07_dup_and_no_space",
        "---\n"
        "title: First\n"
        "title: Second\n"
        "tags:python\n"
        "---\n"
        "# Body\n",
    ),
    (
        "08_unquoted_special_and_tab",
        "---\n"
        "title: Hello\n"
        "command: @run\n"
        "tags:\n"
        "\t- yaml\n"
        "---\n"
        "# Body\n",
    ),
]


def _run_demo() -> int:
    print("# llm-output-markdown-yaml-frontmatter-validator"
          " — worked example")
    print()
    any_failed = False
    for name, src in _CASES:
        print(f"## case {name}")
        print(f"input_lines: {len(src.splitlines())}")
        report = check(src)
        if not report.ok:
            any_failed = True
        print(report.to_json())
        print()
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(_run_demo())
