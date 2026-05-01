#!/usr/bin/env python3
"""Detect AWS IAM policy documents that grant overly broad permissions
via wildcard ``Action`` (or ``NotAction``) on an ``Allow`` statement,
particularly when paired with a wildcard ``Resource``.

LLM-generated IAM policy JSON routinely produces statements like::

    {
      "Effect": "Allow",
      "Action": "*",
      "Resource": "*"
    }

or the slightly more subtle::

    {
      "Effect": "Allow",
      "Action": ["s3:*", "iam:*"],
      "Resource": "*"
    }

Both are textbook over-privilege. The first is the AWS-managed
``AdministratorAccess`` shape and should never appear in a hand-written
inline policy attached to a workload role. The second still grants full
control over an entire service.

This detector inspects ``.json`` files (and ``*.policy.json``, common
under ``policies/``, ``iam/``, ``terraform/`` trees) that look like IAM
policy documents (``Version`` + ``Statement`` keys), and flags Allow
statements whose ``Action`` / ``NotAction`` is ``"*"`` or contains an
entry of the form ``"<service>:*"`` while ``Resource`` is also ``"*"``.

CWE refs:
  - CWE-269: Improper Privilege Management
  - CWE-732: Incorrect Permission Assignment for Critical Resource
  - CWE-285: Improper Authorization

False-positive surface:
  - Trust policies (``sts:AssumeRole``) and break-glass admin roles
    legitimately need broad permissions. Suppress per file with a
    top-level ``"_iam_wildcard_allowed": true`` sibling of ``Version``,
    or per statement with ``"Sid"`` ending in ``-AdminAllowed``.
  - ``Effect: Deny`` statements with wildcards are safe and ignored.
  - ``NotAction`` with a wildcard inside a ``Deny`` statement is the
    canonical "deny everything except" shape and is ignored; only
    ``Allow`` is flagged.

Usage:
    python3 detector.py <path> [<path> ...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<approx-line>:<reason>``.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, List, Tuple


SUPPRESS_SID_SUFFIX = "-AdminAllowed"


def _line_of(source: str, needle: str, start: int = 0) -> int:
    """Best-effort line number for a JSON fragment, used only for
    user-facing reporting. Returns 1 if not found."""
    idx = source.find(needle, start)
    if idx < 0:
        return 1
    return source.count("\n", 0, idx) + 1


def _is_policy_doc(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    if "Statement" not in obj:
        return False
    stmt = obj["Statement"]
    if isinstance(stmt, dict):
        return "Effect" in stmt or "Action" in stmt or "NotAction" in stmt
    if isinstance(stmt, list):
        return any(isinstance(s, dict) and ("Effect" in s or "Action" in s or "NotAction" in s) for s in stmt)
    return False


def _as_list(v: Any) -> List[Any]:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def _action_is_wildcard(actions: List[Any]) -> Tuple[bool, str]:
    for a in actions:
        if not isinstance(a, str):
            continue
        if a == "*":
            return True, "*"
        # service-level wildcard like "s3:*"
        if re.fullmatch(r"[A-Za-z0-9\-]+:\*", a):
            return True, a
    return False, ""


def _resource_is_wildcard(resources: List[Any]) -> bool:
    for r in resources:
        if isinstance(r, str) and r == "*":
            return True
    return False


def scan_policy(source: str, doc: Any) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if not _is_policy_doc(doc):
        return findings
    if doc.get("_iam_wildcard_allowed") is True:
        return findings
    statements = doc["Statement"]
    if isinstance(statements, dict):
        statements = [statements]
    for stmt in statements:
        if not isinstance(stmt, dict):
            continue
        effect = stmt.get("Effect", "Allow")
        if str(effect).lower() != "allow":
            continue
        sid = stmt.get("Sid", "")
        if isinstance(sid, str) and sid.endswith(SUPPRESS_SID_SUFFIX):
            continue
        actions = _as_list(stmt.get("Action"))
        not_actions = _as_list(stmt.get("NotAction"))
        resources = _as_list(stmt.get("Resource"))
        not_resources = _as_list(stmt.get("NotResource"))

        # NotAction in an Allow is itself a red flag (allow-everything-except)
        if not_actions:
            line = _line_of(source, "NotAction")
            findings.append((line, "Allow + NotAction grants every action except the listed ones"))

        # Resource: if NotResource is *, treat as wildcard resource too.
        wide_resource = _resource_is_wildcard(resources) or _resource_is_wildcard(not_resources) or not (resources or not_resources)

        wild, sample = _action_is_wildcard(actions)
        if wild and wide_resource:
            line = _line_of(source, "Action")
            if sample == "*":
                findings.append((line, "Allow Action=\"*\" with wildcard Resource grants full account access"))
            else:
                findings.append((line, f"Allow Action={sample!r} with wildcard Resource grants full service access"))
        elif wild and not wide_resource:
            # still risky for high-blast-radius services
            if sample.split(":", 1)[0].lower() in {"iam", "sts", "kms", "organizations", "account"}:
                line = _line_of(source, "Action")
                findings.append((line, f"Allow Action={sample!r} on a privileged service is high-blast-radius"))
    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("*.json",):
                targets.extend(sorted(path.rglob(ext)))
        else:
            targets.append(path)
    for f in targets:
        try:
            source = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{f}:0:read-error: {exc}")
            continue
        try:
            doc = json.loads(source)
        except json.JSONDecodeError:
            continue
        hits = scan_policy(source, doc)
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
