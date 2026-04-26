"""Pure-stdlib detector for byte-order-mark (BOM) bytes embedded in LLM output.

A BOM at the start of a UTF-8 stream is permitted by the Unicode standard but
breaks an enormous amount of real tooling: shell scripts whose `#!` is no
longer the first byte, JSON parsers that error on the leading U+FEFF, diff
tools that report a one-byte change on otherwise-identical files, web servers
that serve the BOM into the page and produce a stray glyph at the top of the
rendered HTML. A BOM **mid-stream** is almost always a concatenation accident
(multiple files glued together each kept their own BOM).

This detector operates on the **raw byte stream** because by the time the
text has been decoded to `str` the BOM is already a `U+FEFF` codepoint and
indistinguishable from a deliberate zero-width-no-break-space — which is the
job of `llm-output-zero-width-character-detector`. The byte-level view is the
one that catches the actual file-format bug.

Detected encodings (each is its own finding kind):
    utf8          EF BB BF
    utf16_le      FF FE
    utf16_be      FE FF
    utf32_le      FF FE 00 00
    utf32_be      00 00 FE FF
    utf7          2B 2F 76 38   (and 39, 2B, 2F variants)
    utf1          F7 64 4C
    utf_ebcdic    DD 73 66 73
    scsu          0E FE FF
    bocu1         FB EE 28
    gb18030       84 31 95 33

UTF-32 is checked **before** UTF-16 because the UTF-32-LE BOM begins with the
exact two bytes of the UTF-16-LE BOM; matching UTF-16-LE first would mask
every UTF-32-LE finding.

Severity:
    leading       at byte offset 0 — tolerable for some pipelines, fatal for
                  shell / JSON / SQL files. Operator decides via the
                  `fail_on_leading` flag at the call site.
    mid_stream    anywhere else — almost certainly a bug; nearly always a
                  concatenation of two files.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Tuple


# Ordered: longest signature first within each family, UTF-32 before UTF-16
# because UTF-32-LE shares a prefix with UTF-16-LE.
_BOM_SIGNATURES: Tuple[Tuple[str, bytes], ...] = (
    ("utf32_le", b"\xff\xfe\x00\x00"),
    ("utf32_be", b"\x00\x00\xfe\xff"),
    ("utf8", b"\xef\xbb\xbf"),
    ("utf7", b"\x2b\x2f\x76\x38"),
    ("utf7", b"\x2b\x2f\x76\x39"),
    ("utf7", b"\x2b\x2f\x76\x2b"),
    ("utf7", b"\x2b\x2f\x76\x2f"),
    ("utf1", b"\xf7\x64\x4c"),
    ("utf_ebcdic", b"\xdd\x73\x66\x73"),
    ("scsu", b"\x0e\xfe\xff"),
    ("bocu1", b"\xfb\xee\x28"),
    ("gb18030", b"\x84\x31\x95\x33"),
    ("utf16_le", b"\xff\xfe"),
    ("utf16_be", b"\xfe\xff"),
)


@dataclass(frozen=True)
class Finding:
    offset: int
    kind: str          # encoding name, e.g. "utf8"
    severity: str      # "leading" | "mid_stream"
    bytes_hex: str     # hex of the matched signature, lower-case, space-separated


def detect_boms(data: bytes) -> List[Finding]:
    """Return every BOM occurrence in `data`, sorted by (offset, kind).

    A BOM at offset 0 has severity="leading"; everywhere else, "mid_stream".
    Each byte position is matched at most once: if a longer signature matches
    at offset i, the shorter signatures at i are not also reported.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("detect_boms expects bytes; decode-stage detection "
                        "is the job of zero-width-character-detector")

    findings: List[Finding] = []
    i = 0
    n = len(data)
    while i < n:
        matched_len = 0
        for kind, sig in _BOM_SIGNATURES:
            sl = len(sig)
            if i + sl <= n and data[i:i + sl] == sig:
                severity = "leading" if i == 0 else "mid_stream"
                hex_str = " ".join(f"{b:02x}" for b in sig)
                findings.append(Finding(
                    offset=i, kind=kind, severity=severity, bytes_hex=hex_str,
                ))
                matched_len = sl
                break
        if matched_len:
            i += matched_len
        else:
            i += 1

    findings.sort(key=lambda f: (f.offset, f.kind))
    return findings


def format_report(findings: List[Finding]) -> str:
    """Stable, diff-friendly text report."""
    if not findings:
        return "OK: no BOM bytes found."
    lines = [f"FOUND {len(findings)} BOM occurrence(s):"]
    for f in findings:
        lines.append(
            f"  offset {f.offset}: {f.kind} severity={f.severity} "
            f"bytes=[{f.bytes_hex}]"
        )
    return "\n".join(lines)


def has_blocking_bom(findings: List[Finding], fail_on_leading: bool) -> bool:
    """Policy helper: return True if at least one finding should fail CI.

    Mid-stream BOMs always block. Leading BOMs block only when the operator
    has set fail_on_leading=True (e.g. shell-script / JSON pipelines).
    """
    for f in findings:
        if f.severity == "mid_stream":
            return True
        if f.severity == "leading" and fail_on_leading:
            return True
    return False


def finding_as_dict(f: Finding) -> dict:
    """Convenience for JSON / structured-log pipelines."""
    return asdict(f)
