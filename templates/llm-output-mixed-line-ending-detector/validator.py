"""Pure-stdlib detector for mixed line endings in an LLM output blob.

A "line ending" is one of:
  - LF      b"\\n"   (Unix; the canonical form for Markdown / source / git)
  - CRLF    b"\\r\\n" (Windows; sometimes leaked when a model is trained
                       on Windows-authored text or when a copy-paste
                       round-trips through a Windows clipboard tool)
  - CR      b"\\r"    (legacy classic-Mac; almost always a model artifact
                       when seen in 2024+ output)

Findings:
  - `mixed_endings`     — the blob contains MORE THAN ONE distinct
                          line-ending kind. Reported once with the
                          inventory.
  - `cr_only`           — a bare CR (not part of CRLF) on a specific
                          line. Reported per occurrence with the
                          1-based line number.
  - `crlf_in_lf_blob`   — a single CRLF embedded in an otherwise LF
                          blob. Reported per occurrence.
  - `lf_in_crlf_blob`   — a single LF embedded in an otherwise CRLF
                          blob. Reported per occurrence.
  - `trailing_no_eol`   — final byte of the blob is not a line ending
                          (only reported if the blob is non-empty).

Pure: input is `str`, no I/O, no third-party deps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


class ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Finding:
    kind: str
    line_number: int
    detail: str


_KINDS = ("mixed_endings", "cr_only", "crlf_in_lf_blob", "lf_in_crlf_blob", "trailing_no_eol")


def _scan_endings(text: str):
    """Return (lf, crlf, cr_only, positions) where positions is a list of
    (kind, line_number_of_the_terminator)."""
    lf = 0
    crlf = 0
    cr_only = 0
    positions = []
    line_no = 1
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\r":
            if i + 1 < n and text[i + 1] == "\n":
                crlf += 1
                positions.append(("crlf", line_no))
                line_no += 1
                i += 2
                continue
            cr_only += 1
            positions.append(("cr", line_no))
            line_no += 1
            i += 1
            continue
        if ch == "\n":
            lf += 1
            positions.append(("lf", line_no))
            line_no += 1
            i += 1
            continue
        i += 1
    return lf, crlf, cr_only, positions


def detect_line_ending_issues(text: str) -> List[Finding]:
    if not isinstance(text, str):
        raise ValidationError(f"text must be str, got {type(text).__name__}")
    findings: List[Finding] = []
    if text == "":
        return findings

    lf, crlf, cr_only, positions = _scan_endings(text)
    distinct = sum(1 for c in (lf, crlf, cr_only) if c > 0)

    # mixed_endings summary (reported once, line_number=0 = blob-scope)
    if distinct > 1:
        findings.append(
            Finding(
                kind="mixed_endings",
                line_number=0,
                detail=f"blob contains {distinct} distinct line-ending kinds: lf={lf} crlf={crlf} cr_only={cr_only}",
            )
        )

    # Decide majority for "X_in_Y_blob" reports.
    # If only one kind is present we skip the per-line embedding noise.
    if distinct >= 2:
        # majority: largest count. Ties broken lf > crlf > cr_only.
        majority = max(("lf", lf), ("crlf", crlf), ("cr", cr_only), key=lambda kv: kv[1])[0]
        for kind, ln in positions:
            if kind == majority:
                continue
            if majority == "lf" and kind == "crlf":
                findings.append(
                    Finding(kind="crlf_in_lf_blob", line_number=ln, detail="CRLF terminator inside an LF-majority blob")
                )
            elif majority == "crlf" and kind == "lf":
                findings.append(
                    Finding(kind="lf_in_crlf_blob", line_number=ln, detail="bare LF terminator inside a CRLF-majority blob")
                )
            elif kind == "cr":
                findings.append(
                    Finding(kind="cr_only", line_number=ln, detail="bare CR (classic-Mac) terminator")
                )
    else:
        # Single kind, but cr_only on its own is still noteworthy.
        if cr_only > 0 and lf == 0 and crlf == 0:
            for kind, ln in positions:
                if kind == "cr":
                    findings.append(
                        Finding(kind="cr_only", line_number=ln, detail="bare CR (classic-Mac) terminator")
                    )

    # trailing_no_eol: blob is non-empty and last byte is not LF or CR
    last = text[-1]
    if last not in ("\n", "\r"):
        # report at the line number of the unterminated final line
        # which is len(positions) + 1 (terminators consumed so far + 1)
        findings.append(
            Finding(
                kind="trailing_no_eol",
                line_number=len(positions) + 1,
                detail="final line is not terminated by a line ending",
            )
        )

    findings.sort(key=lambda f: (f.line_number, _KINDS.index(f.kind) if f.kind in _KINDS else 99))
    return findings


def format_report(findings: List[Finding]) -> str:
    if not findings:
        return "OK: line endings are consistent.\n"
    lines = [f"FOUND {len(findings)} line-ending finding(s):"]
    for f in findings:
        loc = f"line={f.line_number}" if f.line_number > 0 else "scope=blob"
        lines.append(f"  [{f.kind}] {loc} :: {f.detail}")
    lines.append("")
    return "\n".join(lines)


__all__ = ["Finding", "ValidationError", "detect_line_ending_issues", "format_report"]
