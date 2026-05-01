#!/usr/bin/env python3
"""Detect Terraform HCL that exposes an AWS S3 bucket to the public
internet via a permissive ACL, a disabled public-access-block, a
wildcard ``Principal`` policy, or a wildcard CORS configuration.

The shapes flagged are CWE-732 / CWE-284 footguns an LLM emits when
asked for "a quick S3 bucket to drop files into".

See README.md for the full set of shapes and suppression markers.

Stdlib only. Exit code 1 if any findings, 0 otherwise.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "# llm-allow:tf-s3-public"

SCAN_SUFFIXES = (".tf", ".md", ".markdown")


# ---------------------------------------------------------------------------
# Markdown fence extraction.
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(
    r"^([ \t]{0,3})(```+|~~~+)[ \t]*([A-Za-z0-9_+\-.]*)[^\n]*\n(.*?)(?:^\1\2[ \t]*$)",
    re.DOTALL | re.MULTILINE,
)
_TF_LANGS = {"hcl", "terraform", "tf"}


def _iter_tf_blocks(text: str):
    for m in _FENCE_RE.finditer(text):
        lang = (m.group(3) or "").strip().lower()
        if lang in _TF_LANGS:
            body_start = m.start(4)
            line_offset = text.count("\n", 0, body_start)
            yield m.group(4), line_offset


# ---------------------------------------------------------------------------
# Comment masking. HCL supports `#` and `//` line comments and `/* */`
# block comments. We strip them before applying shape regexes.
# ---------------------------------------------------------------------------

def _strip_block_comments(text: str) -> str:
    out = []
    i = 0
    n = len(text)
    in_d = False  # inside double-quoted string
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            out.append(text[i:i + 2])
            i += 2
            continue
        if ch == '"' and not _prev_is_dollar_brace(text, i):
            in_d = not in_d
            out.append(ch)
            i += 1
            continue
        if not in_d and text[i:i + 2] == "/*":
            j = text.find("*/", i + 2)
            if j == -1:
                # Unclosed; keep newlines for line-number stability
                rest = text[i:]
                out.append(re.sub(r"[^\n]", " ", rest))
                break
            blk = text[i:j + 2]
            out.append(re.sub(r"[^\n]", " ", blk))
            i = j + 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _prev_is_dollar_brace(text: str, i: int) -> bool:
    # Avoid toggling on `"` that is part of HCL interpolation tokens —
    # not actually needed for correctness but harmless.
    return False


def _mask_line_comments(line: str) -> str:
    in_s = False
    in_d = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line):
            i += 2
            continue
        if not in_s and ch == '"':
            in_d = not in_d
        elif not in_d and ch == "'":
            in_s = not in_s
        elif not in_s and not in_d:
            if ch == "#":
                return line[:i] + " " * (len(line) - i)
            if ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
                return line[:i] + " " * (len(line) - i)
        i += 1
    return line


# ---------------------------------------------------------------------------
# Resource block extraction. We need to know which resource type a line
# belongs to so we only flag, e.g., `acl = "public-read"` inside an
# aws_s3_bucket / aws_s3_bucket_acl block.
# ---------------------------------------------------------------------------

_RESOURCE_HEADER_RE = re.compile(
    r'^\s*resource\s+"([A-Za-z0-9_]+)"\s+"([A-Za-z0-9_]+)"\s*\{'
)


def _walk_blocks(masked_lines):
    """Yield (line_no_1based, resource_type, resource_name, line_text)
    for each line that lives inside a top-level resource block.

    Lines outside any resource block yield (line_no, None, None, line).
    Brace tracking is depth-counted on masked lines; strings have been
    stripped of comments but not of literal `{` / `}` inside string
    values. For our shapes that's fine because S3 resource bodies
    don't put unbalanced braces in string values.
    """
    cur_type = None
    cur_name = None
    depth = 0
    for idx, line in enumerate(masked_lines):
        line_no = idx + 1
        if cur_type is None:
            m = _RESOURCE_HEADER_RE.match(line)
            if m:
                cur_type = m.group(1)
                cur_name = m.group(2)
                depth = line.count("{") - line.count("}")
                yield line_no, cur_type, cur_name, line
                if depth <= 0:
                    cur_type = None
                    cur_name = None
                    depth = 0
                continue
            yield line_no, None, None, line
        else:
            depth += line.count("{") - line.count("}")
            yield line_no, cur_type, cur_name, line
            if depth <= 0:
                cur_type = None
                cur_name = None
                depth = 0


# ---------------------------------------------------------------------------
# Shape regexes.
# ---------------------------------------------------------------------------

_PUBLIC_ACLS = ("public-read", "public-read-write", "authenticated-read")
_ACL_RE = re.compile(r'^\s*acl\s*=\s*"([^"]+)"')
_PAB_BOOL_RE = re.compile(
    r'^\s*(block_public_acls|block_public_policy|ignore_public_acls|restrict_public_buckets)\s*=\s*(false)\b'
)
_BUCKET_DECL_RE = re.compile(r'^\s*bucket\s*=\s*"([A-Za-z0-9_.\-]+)"')
_PRINCIPAL_WILDCARD_RES = (
    re.compile(r'"Principal"\s*:\s*"\*"'),
    re.compile(r'"Principal"\s*:\s*\{\s*"AWS"\s*:\s*"\*"\s*\}'),
    re.compile(r'Principal\s*=\s*"\*"'),
)
_CONDITION_RE = re.compile(r'"Condition"\s*:')
_CORS_ALLOWED_ORIGINS_RE = re.compile(r'allowed_origins\s*=\s*\[\s*"\*"\s*\]')


# ---------------------------------------------------------------------------
# Per-text scanner. ``text`` is HCL source (possibly extracted from
# Markdown). ``start_line`` lets us report Markdown-relative line
# numbers.
# ---------------------------------------------------------------------------

def _scan_text(text: str, start_line: int = 0):
    text = _strip_block_comments(text)
    raw_lines = text.splitlines()
    masked_lines = [_mask_line_comments(l) for l in raw_lines]

    findings = []  # list of (line_no_relative, kind)
    s3_buckets_declared_lines = []
    pab_present = False

    # Track per-resource policy aggregation for principal-wildcard +
    # absence-of-Condition.
    cur_policy_block = None  # (start_line, lines_collected)

    for line_no, rtype, _rname, line in _walk_blocks(masked_lines):
        raw = raw_lines[line_no - 1]
        if SUPPRESS in raw:
            continue

        # Track presence of public_access_block resource anywhere in file.
        if rtype == "aws_s3_bucket_public_access_block":
            pab_present = True

        # Shape 1: tf-s3-acl-public
        if rtype in ("aws_s3_bucket", "aws_s3_bucket_acl"):
            m = _ACL_RE.match(line)
            if m and m.group(1) in _PUBLIC_ACLS:
                findings.append((line_no, "tf-s3-acl-public"))

        # Track aws_s3_bucket "bucket = ..." for missing-PAB heuristic.
        if rtype == "aws_s3_bucket":
            m = _BUCKET_DECL_RE.match(line)
            if m:
                s3_buckets_declared_lines.append(line_no)

        # Shape 2: tf-s3-pab-disabled
        if rtype == "aws_s3_bucket_public_access_block":
            m = _PAB_BOOL_RE.match(line)
            if m:
                findings.append((line_no, "tf-s3-pab-disabled"))

        # Shape 6: tf-s3-cors-allow-all-origins
        if rtype == "aws_s3_bucket_cors_configuration":
            if _CORS_ALLOWED_ORIGINS_RE.search(line):
                findings.append((line_no, "tf-s3-cors-allow-all-origins"))

        # Shape 4: tf-s3-policy-principal-wildcard.
        # We aggregate inside aws_s3_bucket_policy blocks and check
        # whether the block as a whole has any "Condition" key.
        if rtype == "aws_s3_bucket_policy":
            if cur_policy_block is None:
                cur_policy_block = (line_no, [])
            cur_policy_block[1].append((line_no, line))
        else:
            if cur_policy_block is not None:
                _flush_policy_block(cur_policy_block, findings)
                cur_policy_block = None

    if cur_policy_block is not None:
        _flush_policy_block(cur_policy_block, findings)

    # Shape 3: tf-s3-pab-missing
    if s3_buckets_declared_lines and not pab_present:
        findings.append((s3_buckets_declared_lines[0], "tf-s3-pab-missing"))

    # Adjust for Markdown line offset.
    return [(start_line + ln, kind) for ln, kind in findings]


def _flush_policy_block(block, findings):
    _start_line, lines = block
    body = "\n".join(l for _, l in lines)
    has_condition = bool(_CONDITION_RE.search(body))
    if has_condition:
        return
    for line_no, line in lines:
        for rx in _PRINCIPAL_WILDCARD_RES:
            if rx.search(line):
                findings.append((line_no, "tf-s3-policy-principal-wildcard"))
                break


# ---------------------------------------------------------------------------
# File scanner.
# ---------------------------------------------------------------------------

def scan_file(path: Path):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"{path}: error: {exc}", file=sys.stderr)
        return []
    suffix = path.suffix.lower()
    findings = []
    if suffix in (".md", ".markdown"):
        for body, line_offset in _iter_tf_blocks(text):
            findings.extend(_scan_text(body, start_line=line_offset))
    else:
        findings.extend(_scan_text(text))
    return findings


def _iter_paths(roots):
    for root in roots:
        p = Path(root)
        if p.is_file():
            yield p
        elif p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and sub.suffix.lower() in SCAN_SUFFIXES:
                    yield sub


def main(argv):
    if len(argv) < 2:
        print("usage: detect.py <file_or_dir> [...]", file=sys.stderr)
        return 2
    any_findings = False
    for path in _iter_paths(argv[1:]):
        for line_no, kind in scan_file(path):
            print(f"{path}:{line_no}: {kind}: terraform aws_s3 public-exposure shape")
            any_findings = True
    return 1 if any_findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
