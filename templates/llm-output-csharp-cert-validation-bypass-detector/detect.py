#!/usr/bin/env python3
"""Detect TLS certificate-validation bypass patterns in LLM-emitted C#.

Patterns flagged
----------------
1. ``ServicePointManager.ServerCertificateValidationCallback = ... => true``
   (or any lambda / delegate whose body trivially returns ``true``).
2. ``ServerCertificateCustomValidationCallback =
   HttpClientHandler.DangerousAcceptAnyServerCertificateValidator``.
3. ``ServerCertificateCustomValidationCallback = (...) => true`` (or
   block body that just returns ``true``).
4. ``RemoteCertificateValidationCallback`` lambdas with the same shape
   (used with ``SslStream``).

CWE references
--------------
* **CWE-295**: Improper Certificate Validation.
* **CWE-297**: Improper Validation of Certificate with Host Mismatch.
* **CWE-345**: Insufficient Verification of Data Authenticity.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit 1 if any findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "// cert-validation-ok"

CALLBACK_NAMES = (
    "ServerCertificateValidationCallback",
    "ServerCertificateCustomValidationCallback",
    "RemoteCertificateValidationCallback",
)

# Property assignment / object-initializer entry of one of the callback names.
RE_CALLBACK_ASSIGN = re.compile(
    r"\b(?:" + "|".join(CALLBACK_NAMES) + r")\s*=\s*(.*)$"
)

# Dangerous canned validator.
RE_DANGEROUS_VALIDATOR = re.compile(
    r"\bHttpClientHandler\s*\.\s*DangerousAcceptAnyServerCertificateValidator\b"
)

# `(args) => true` or `(args) => { return true; }` or `delegate(args){return true;}`.
RE_LAMBDA_TRUE = re.compile(
    r"=>\s*true\b"
)
RE_BLOCK_RETURN_TRUE = re.compile(r"=>\s*\{\s*return\s+true\s*;\s*\}")
RE_DELEGATE_RETURN_TRUE = re.compile(
    r"\bdelegate\s*\([^)]*\)\s*\{\s*return\s+true\s*;\s*\}"
)


def _strip_strings_and_comments(line: str) -> str:
    out: list[str] = []
    i = 0
    n = len(line)
    in_s = False
    in_c = False
    while i < n:
        ch = line[i]
        if in_s:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == '"':
                in_s = False
                out.append('"')
            else:
                out.append(" ")
        elif in_c:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == "'":
                in_c = False
                out.append("'")
            else:
                out.append(" ")
        else:
            if ch == "/" and i + 1 < n and line[i + 1] == "/":
                break
            if ch == '"':
                in_s = True
                out.append('"')
            elif ch == "'":
                in_c = True
                out.append("'")
            else:
                out.append(ch)
        i += 1
    return "".join(out)


def _line_is_unsafe(stripped: str) -> str | None:
    """Return finding-kind if line is unsafe, else None.

    Operates on the string-and-comment-stripped line.
    """
    m = RE_CALLBACK_ASSIGN.search(stripped)
    if not m:
        return None
    rhs = m.group(1)
    # Trim trailing punctuation that may belong to outer initializer.
    rhs_trim = rhs.rstrip().rstrip(",;")
    if RE_DANGEROUS_VALIDATOR.search(rhs_trim):
        return "dangerous-accept-any-validator"
    if RE_BLOCK_RETURN_TRUE.search(rhs_trim):
        return "callback-return-true-lambda-block"
    if RE_LAMBDA_TRUE.search(rhs_trim):
        return "callback-return-true-lambda"
    if RE_DELEGATE_RETURN_TRUE.search(rhs_trim):
        return "callback-return-true-delegate"
    return None


RE_CALLBACK_CTOR = re.compile(
    r"\bnew\s+RemoteCertificateValidationCallback\s*\("
)

# Property initializer / auto-property: `<CallbackType> Name {...} = <rhs>` or
# `<CallbackType> Name = <rhs>`. We look for any line containing one of the
# callback names followed (anywhere later) by `= <rhs>` and a trivially-true
# body. Done as a permissive secondary pass.
RE_CALLBACK_NAME_ANYWHERE = re.compile(r"\b(?:" + "|".join(CALLBACK_NAMES) + r")\b")


def _gather_logical_line(lines: list[str], start: int) -> tuple[str, int]:
    """Join continuation lines starting at index ``start`` until a ``;`` or
    a top-level ``}`` is found (whichever comes first). Returns the joined
    string-stripped text and the number of physical lines consumed.
    """
    joined: list[str] = []
    consumed = 0
    depth = 0
    for k in range(start, min(start + 8, len(lines))):
        s = _strip_strings_and_comments(lines[k])
        joined.append(s)
        consumed += 1
        for ch in s:
            if ch in "({[":
                depth += 1
            elif ch in ")}]":
                depth -= 1
        if ";" in s and depth <= 0:
            break
    return (" ".join(joined), consumed)


def scan_file(path: Path) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings

    lines = text.splitlines()
    flagged_lines: set[int] = set()
    for lineno, raw in enumerate(lines, start=1):
        if SUPPRESS in raw:
            continue
        if lineno in flagged_lines:
            continue
        stripped = _strip_strings_and_comments(raw)

        kind = _line_is_unsafe(stripped)
        if kind:
            findings.append((path, lineno, kind, raw.rstrip()))
            flagged_lines.add(lineno)
            continue

        # Constructor form: `new RemoteCertificateValidationCallback((..) => true)`.
        if RE_CALLBACK_CTOR.search(stripped):
            joined, consumed = _gather_logical_line(lines, lineno - 1)
            if (
                RE_LAMBDA_TRUE.search(joined)
                or RE_BLOCK_RETURN_TRUE.search(joined)
                or RE_DELEGATE_RETURN_TRUE.search(joined)
            ):
                findings.append(
                    (path, lineno, "callback-ctor-return-true", raw.rstrip())
                )
                for k in range(lineno, lineno + consumed):
                    flagged_lines.add(k)
                continue

        # Permissive secondary pass: callback name appears with `=` somewhere
        # on this logical line and the rest reduces to trivial-true / dangerous
        # validator. Catches multiline RHS, property initializers, and
        # delegate forms in one shot.
        if RE_CALLBACK_NAME_ANYWHERE.search(stripped) and "=" in stripped:
            joined, consumed = _gather_logical_line(lines, lineno - 1)
            # Check for SUPPRESS in any consumed line.
            suppressed = any(
                SUPPRESS in lines[k]
                for k in range(lineno - 1, min(lineno - 1 + consumed, len(lines)))
            )
            if suppressed:
                continue
            if RE_DANGEROUS_VALIDATOR.search(joined):
                findings.append(
                    (path, lineno, "dangerous-accept-any-validator", raw.rstrip())
                )
                for k in range(lineno, lineno + consumed):
                    flagged_lines.add(k)
                continue
            if RE_BLOCK_RETURN_TRUE.search(joined):
                findings.append(
                    (
                        path,
                        lineno,
                        "callback-return-true-lambda-multiline-block",
                        raw.rstrip(),
                    )
                )
                for k in range(lineno, lineno + consumed):
                    flagged_lines.add(k)
                continue
            if RE_DELEGATE_RETURN_TRUE.search(joined):
                findings.append(
                    (
                        path,
                        lineno,
                        "callback-return-true-delegate",
                        raw.rstrip(),
                    )
                )
                for k in range(lineno, lineno + consumed):
                    flagged_lines.add(k)
                continue
            if RE_LAMBDA_TRUE.search(joined):
                findings.append(
                    (
                        path,
                        lineno,
                        "callback-return-true-lambda-multiline",
                        raw.rstrip(),
                    )
                )
                for k in range(lineno, lineno + consumed):
                    flagged_lines.add(k)
                continue
    return findings


def iter_paths(args: list[str]) -> list[Path]:
    out: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            for sub in sorted(p.rglob("*.cs")):
                out.append(sub)
    return out


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detect.py <file_or_dir> [...]", file=sys.stderr)
        return 2
    findings: list[tuple[Path, int, str, str]] = []
    for path in iter_paths(argv[1:]):
        findings.extend(scan_file(path))
    for path, lineno, kind, line in findings:
        print(f"{path}:{lineno}: {kind}: {line}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
