#!/usr/bin/env python3
"""Detect overly-permissive AWS security-group ingress in LLM-emitted Terraform.

CWE-732 / CWE-284. LLMs writing AWS Terraform routinely emit::

    resource "aws_security_group" "db" {
      ingress {
        from_port   = 22
        to_port     = 22
        protocol    = "tcp"
        cidr_blocks = ["0.0.0.0/0"]
      }
    }

…or the standalone ``aws_security_group_rule`` / ``aws_vpc_security_group_ingress_rule``
form. Opening ``0.0.0.0/0`` (or ``::/0``) to a sensitive admin port —
SSH, RDP, database, Kubernetes API, container registries, message
brokers, internal HTTP admin panels — is the textbook
network-misconfiguration finding flagged by every cloud auditor.

What this flags
---------------
A ``.tf`` (or ``.tf.json`` ignored — HCL only) file that contains an
ingress block whose CIDR list includes ``0.0.0.0/0`` or ``::/0`` AND
whose port range overlaps any of these sensitive admin / data ports::

    22, 23, 25, 110, 135, 139, 445, 1433, 1521, 2049, 2375, 2376,
    3306, 3389, 4505, 4506, 5432, 5601, 5672, 5984, 6379, 6443,
    7001, 7199, 8020, 8086, 8088, 8443, 8500, 9000, 9042, 9092,
    9200, 9300, 11211, 15672, 25565, 27017, 27018, 50070

Forms recognised:

* nested ``ingress { ... cidr_blocks = ["0.0.0.0/0"] ... }`` inside
  ``resource "aws_security_group" "<name>" { ... }``
* standalone ``resource "aws_security_group_rule" "<name>" { type =
  "ingress" ... cidr_blocks = ["0.0.0.0/0"] ... }``
* ``resource "aws_vpc_security_group_ingress_rule" "<name>"`` with
  ``cidr_ipv4 = "0.0.0.0/0"`` (single string, not a list)

What this does NOT flag
-----------------------
* Egress rules.
* Ingress restricted to an org CIDR (``10.0.0.0/8``, a VPC CIDR var, etc.).
* Ports 80 / 443 / 8080 — those are documented public web tiers and
  flagging them produces false positives at scale.
* Blocks tagged with ``# sg-open-ok`` on the ``ingress`` / resource line.
* Files that contain the marker comment ``# tfsec:ignore:sg-open`` or
  ``# checkov:skip=sg-open`` anywhere (interop with existing tooling).

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit 1 on findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS_LINE = "# sg-open-ok"
SUPPRESS_FILE = ("# tfsec:ignore:sg-open", "# checkov:skip=sg-open")

SENSITIVE_PORTS = {
    22, 23, 25, 110, 135, 139, 445, 1433, 1521, 2049, 2375, 2376,
    3306, 3389, 4505, 4506, 5432, 5601, 5672, 5984, 6379, 6443,
    7001, 7199, 8020, 8086, 8088, 8443, 8500, 9000, 9042, 9092,
    9200, 9300, 11211, 15672, 25565, 27017, 27018, 50070,
}

OPEN_CIDRS = ("0.0.0.0/0", "::/0")


def _strip_line_comment(line: str) -> str:
    # HCL line comments: # and //
    out: list[str] = []
    i = 0
    n = len(line)
    in_s = False
    while i < n:
        ch = line[i]
        if in_s:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == '"':
                in_s = False
            out.append(ch)
            i += 1
            continue
        if ch == '"':
            in_s = True
            out.append(ch)
            i += 1
            continue
        if ch == "#":
            break
        if ch == "/" and i + 1 < n and line[i + 1] == "/":
            break
        out.append(ch)
        i += 1
    return "".join(out)


def _split_top_level_blocks(text: str) -> list[tuple[int, str]]:
    """Yield (start_line, block_text) for each top-level brace block.

    A "block" begins at a line that contains an unmatched '{' and ends
    at the line where the matching '}' closes. We treat the entire
    file as one stream and emit each top-level block individually.
    """
    blocks: list[tuple[int, str]] = []
    lines = text.splitlines()
    depth = 0
    start = -1
    buf: list[str] = []
    for i, raw in enumerate(lines, start=1):
        stripped = _strip_line_comment(raw)
        opens = stripped.count("{")
        closes = stripped.count("}")
        if depth == 0 and opens > 0:
            start = i
            buf = [raw]
            depth = opens - closes
            if depth == 0 and opens > 0:
                blocks.append((start, "\n".join(buf)))
                buf = []
                start = -1
            continue
        if depth > 0:
            buf.append(raw)
            depth += opens - closes
            if depth <= 0:
                blocks.append((start, "\n".join(buf)))
                buf = []
                start = -1
                depth = 0
    return blocks


RE_RESOURCE_HEADER = re.compile(
    r'^\s*resource\s+"([a-zA-Z0-9_]+)"\s+"([a-zA-Z0-9_\-]+)"\s*\{'
)


def _find_inner_blocks(text: str, header: str) -> list[tuple[int, str]]:
    """Find nested blocks of the given header name (e.g. 'ingress')
    inside `text`, returning (relative_line_no, block_text)."""
    out: list[tuple[int, str]] = []
    lines = text.splitlines()
    i = 0
    n = len(lines)
    pat = re.compile(r"^\s*" + re.escape(header) + r"\s*\{")
    while i < n:
        if pat.match(_strip_line_comment(lines[i])):
            depth = 0
            buf: list[str] = []
            start = i
            j = i
            while j < n:
                stripped = _strip_line_comment(lines[j])
                buf.append(lines[j])
                depth += stripped.count("{") - stripped.count("}")
                if depth == 0:
                    break
                j += 1
            out.append((start + 1, "\n".join(buf)))
            i = j + 1
            continue
        i += 1
    return out


def _extract_assignment(block: str, key: str) -> str | None:
    pat = re.compile(
        r"^\s*" + re.escape(key) + r"\s*=\s*(.+?)\s*$",
        re.MULTILINE,
    )
    m = pat.search(block)
    if not m:
        return None
    return m.group(1)


def _has_open_cidr(value: str) -> bool:
    return any(c in value for c in OPEN_CIDRS)


def _port_range(block: str) -> tuple[int, int] | None:
    fp = _extract_assignment(block, "from_port")
    tp = _extract_assignment(block, "to_port")
    if fp is None or tp is None:
        # try the new aws_vpc_security_group_ingress_rule keys
        fp = fp or _extract_assignment(block, "from_port")
        tp = tp or _extract_assignment(block, "to_port")
    try:
        if fp is None or tp is None:
            return None
        return int(fp.strip()), int(tp.strip())
    except ValueError:
        return None


def _range_hits_sensitive(lo: int, hi: int) -> int | None:
    if lo > hi:
        lo, hi = hi, lo
    # fully-open shortcut: a 0-65535 / -1 / 1-65535 range is itself a
    # finding even if no individual sensitive port is named.
    if lo <= 0 and hi >= 65535:
        return -1
    for p in SENSITIVE_PORTS:
        if lo <= p <= hi:
            return p
    return None


def _block_has_line_suppress(block: str) -> bool:
    return SUPPRESS_LINE in block


def scan_file(path: Path) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    if any(tok in text for tok in SUPPRESS_FILE):
        return findings

    for start_line, block in _split_top_level_blocks(text):
        header_match = RE_RESOURCE_HEADER.match(block)
        if not header_match:
            continue
        rtype = header_match.group(1)
        rname = header_match.group(2)

        if rtype == "aws_security_group":
            for rel, sub in _find_inner_blocks(block, "ingress"):
                if _block_has_line_suppress(sub):
                    continue
                cidrs = _extract_assignment(sub, "cidr_blocks") or ""
                cidrs6 = _extract_assignment(sub, "ipv6_cidr_blocks") or ""
                if not (_has_open_cidr(cidrs) or _has_open_cidr(cidrs6)):
                    continue
                pr = _port_range(sub)
                if pr is None:
                    continue
                hit = _range_hits_sensitive(*pr)
                if hit is None:
                    continue
                kind = (
                    f"sg-open-port-{hit}" if hit >= 0 else "sg-open-all-ports"
                )
                findings.append(
                    (path, start_line + rel - 1, kind, f"aws_security_group.{rname}.ingress")
                )

        elif rtype == "aws_security_group_rule":
            if _block_has_line_suppress(block):
                continue
            stype = _extract_assignment(block, "type") or ""
            if '"ingress"' not in stype:
                continue
            cidrs = _extract_assignment(block, "cidr_blocks") or ""
            cidrs6 = _extract_assignment(block, "ipv6_cidr_blocks") or ""
            if not (_has_open_cidr(cidrs) or _has_open_cidr(cidrs6)):
                continue
            pr = _port_range(block)
            if pr is None:
                continue
            hit = _range_hits_sensitive(*pr)
            if hit is None:
                continue
            kind = f"sg-open-port-{hit}" if hit >= 0 else "sg-open-all-ports"
            findings.append(
                (path, start_line, kind, f"aws_security_group_rule.{rname}")
            )

        elif rtype == "aws_vpc_security_group_ingress_rule":
            if _block_has_line_suppress(block):
                continue
            cidr4 = _extract_assignment(block, "cidr_ipv4") or ""
            cidr6 = _extract_assignment(block, "cidr_ipv6") or ""
            if not (_has_open_cidr(cidr4) or _has_open_cidr(cidr6)):
                continue
            pr = _port_range(block)
            if pr is None:
                continue
            hit = _range_hits_sensitive(*pr)
            if hit is None:
                continue
            kind = f"sg-open-port-{hit}" if hit >= 0 else "sg-open-all-ports"
            findings.append(
                (path, start_line, kind, f"aws_vpc_security_group_ingress_rule.{rname}")
            )

    return findings


def iter_paths(args: list[str]) -> list[Path]:
    out: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            for sub in sorted(p.rglob("*.tf")):
                out.append(sub)
    return out


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: detect.py <file_or_dir> [...]", file=sys.stderr)
        return 2
    findings: list[tuple[Path, int, str, str]] = []
    for path in iter_paths(argv[1:]):
        findings.extend(scan_file(path))
    for path, lineno, kind, ctx in findings:
        print(f"{path}:{lineno}: {kind}: {ctx}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
