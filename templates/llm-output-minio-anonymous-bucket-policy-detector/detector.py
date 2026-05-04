#!/usr/bin/env python3
"""Detect MinIO / S3-style bucket policy JSON files that grant
anonymous (``Principal: *``) write or list access, or grant anonymous
``s3:*`` on the bucket — the shape ``mc anonymous set public`` ships
and that LLM-generated quickstarts copy verbatim.

Rules: a finding is emitted for any ``Allow`` statement whose
Principal evaluates to anonymous (``"*"`` or ``{"AWS": "*"}``) and
whose action set includes any of:

* ``s3:*`` (full anonymous control)
* ``s3:PutObject`` / ``s3:DeleteObject`` / ``s3:PutObjectAcl``
  (anonymous writes)
* ``s3:ListBucket`` (anonymous bucket enumeration)

Anonymous ``s3:GetObject`` *alone*, with a ``Resource`` that targets
object keys (``arn:aws:s3:::bucket/*``), is NOT flagged — that is the
documented "public read-only static site" pattern. The same action
against the bucket ARN itself (``arn:aws:s3:::bucket``) IS flagged.

A magic comment ``// minio-anonymous-allowed`` (or
``"_comment": "minio-anonymous-allowed"``) at the top of the file
suppresses the finding.

Stdlib-only. Exit code is the count of files with at least one finding
(capped at 255). Stdout lines have the form ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"minio-anonymous-allowed")

WRITE_ACTIONS = {
    "s3:putobject",
    "s3:deleteobject",
    "s3:putobjectacl",
    "s3:deletebucket",
    "s3:putbucketpolicy",
}
LIST_ACTIONS = {"s3:listbucket", "s3:listbucketmultipartuploads"}
WILDCARD_ACTIONS = {"s3:*", "*"}


def _strip_jsonc(source: str) -> str:
    # Strip // line comments outside strings (mc CLI accepts JSON, but
    # users sometimes leave a // marker comment).
    out = []
    i = 0
    in_str = False
    esc = False
    while i < len(source):
        ch = source[i]
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < len(source) and source[i + 1] == "/":
            while i < len(source) and source[i] != "\n":
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _as_list(v) -> List:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def _is_anonymous(principal) -> bool:
    if principal == "*":
        return True
    if isinstance(principal, dict):
        for k, v in principal.items():
            for item in _as_list(v):
                if item == "*":
                    return True
    if isinstance(principal, list):
        return any(_is_anonymous(p) for p in principal)
    return False


def _resource_targets_bucket_root(resources: List[str]) -> bool:
    """True if any resource is a bucket-level ARN (no /path suffix)."""
    for r in resources:
        if not isinstance(r, str):
            continue
        if not r.startswith("arn:aws:s3:::") and r != "*":
            continue
        if r == "*":
            return True
        rest = r[len("arn:aws:s3:::"):]
        if "/" not in rest:
            return True
    return False


def _line_of_statement_index(source: str, idx: int) -> int:
    # Find the (idx+1)-th '"Effect"' occurrence — close enough for a
    # line anchor.
    pat = re.compile(r'"Effect"\s*:', re.IGNORECASE)
    matches = list(pat.finditer(source))
    if idx < len(matches):
        return source.count("\n", 0, matches[idx].start()) + 1
    return 1


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings
    cleaned = _strip_jsonc(source)
    try:
        doc = json.loads(cleaned)
    except json.JSONDecodeError:
        return findings
    if not isinstance(doc, dict):
        return findings
    statements = _as_list(doc.get("Statement"))
    if not statements:
        return findings

    for i, stmt in enumerate(statements):
        if not isinstance(stmt, dict):
            continue
        if str(stmt.get("Effect", "")).lower() != "allow":
            continue
        if not _is_anonymous(stmt.get("Principal")):
            continue
        actions = [str(a).lower() for a in _as_list(stmt.get("Action"))]
        if not actions:
            continue
        resources = _as_list(stmt.get("Resource"))

        bad_reasons: List[str] = []
        if any(a in WILDCARD_ACTIONS for a in actions):
            bad_reasons.append("anonymous Allow on s3:* (full public control)")
        write_hits = [a for a in actions if a in WRITE_ACTIONS]
        if write_hits:
            bad_reasons.append(
                "anonymous write actions: " + ",".join(sorted(set(write_hits)))
            )
        list_hits = [a for a in actions if a in LIST_ACTIONS]
        if list_hits and _resource_targets_bucket_root([str(r) for r in resources]):
            bad_reasons.append(
                "anonymous bucket enumeration: " + ",".join(sorted(set(list_hits)))
            )
        # Anonymous s3:Get* on a bucket-root ARN is also unusual.
        get_on_root = (
            any(a == "s3:getobject" for a in actions)
            and _resource_targets_bucket_root([str(r) for r in resources])
            and not any(
                isinstance(r, str) and r.endswith("/*") for r in resources
            )
        )
        if get_on_root:
            bad_reasons.append(
                "anonymous s3:GetObject targets bucket ARN, not object keys"
            )

        if bad_reasons:
            findings.append((_line_of_statement_index(source, i), "; ".join(bad_reasons)))
    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for pat in ("*policy*.json", "*bucket*.json", "*.minio.json"):
                targets.extend(sorted(path.rglob(pat)))
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
