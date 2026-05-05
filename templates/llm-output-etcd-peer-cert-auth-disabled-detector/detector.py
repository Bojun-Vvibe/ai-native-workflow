#!/usr/bin/env python3
"""Detect etcd YAML config files that expose a non-loopback peer URL
without enforcing peer certificate authentication (intra-cluster mTLS).

The insecure shape we flag:

* ``listen-peer-urls`` (or ``initial-advertise-peer-urls``) contains a
  non-loopback URL on ``http://`` OR on ``https://`` with
  ``peer-transport-security.peer-client-cert-auth: false`` (the
  default), or with ``cert-file`` / ``key-file`` unset.

Loopback-only deployments (``127.0.0.1``, ``::1``, ``localhost``) are
out of scope. A magic comment ``# etcd-no-peer-cert-auth-allowed``
suppresses the finding for documented single-node test clusters.

This module is **stdlib-only** — it parses the small subset of YAML
that real etcd config files use (top-level scalars, inline lists,
single-level block mappings, dash-prefixed sequences).

Exit code is the number of files with at least one finding (capped at
255). Stdout lines have the form ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple
from urllib.parse import urlparse

SUPPRESS = re.compile(r"#\s*etcd-no-peer-cert-auth-allowed")

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "0:0:0:0:0:0:0:1"}


def _strip_comment(line: str) -> str:
    in_s = in_d = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            return line[:i]
    return line


def _unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return v[1:-1]
    return v


def _parse_inline_list(v: str) -> List[str]:
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1]
        return [_unquote(x) for x in inner.split(",") if x.strip()]
    return [_unquote(x) for x in v.split(",") if x.strip()]


class ParsedDoc:
    """Top-level scalars/lists, plus one nesting level under
    ``peer-transport-security``."""

    def __init__(self) -> None:
        self.scalars: dict = {}
        self.lists: dict = {}
        self.pts: dict = {}
        self.line_of: dict = {}


def _parse(source: str) -> ParsedDoc:
    doc = ParsedDoc()
    lines = source.splitlines()
    i = 0
    in_pts = False
    pts_indent = -1
    cur_list_key = None
    cur_list_indent = -1

    while i < len(lines):
        raw = lines[i]
        stripped_full = _strip_comment(raw).rstrip()
        if not stripped_full.strip():
            i += 1
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        body = stripped_full.strip()

        if cur_list_key is not None:
            if body.startswith("- ") and indent >= cur_list_indent:
                doc.lists.setdefault(cur_list_key, []).append(_unquote(body[2:].strip()))
                i += 1
                continue
            elif body == "-":
                i += 1
                continue
            else:
                cur_list_key = None
                cur_list_indent = -1

        if in_pts:
            if indent > pts_indent and ":" in body:
                k, _, v = body.partition(":")
                doc.pts[k.strip()] = _unquote(v)
                doc.line_of.setdefault("peer-transport-security." + k.strip(), i + 1)
                i += 1
                continue
            elif indent <= pts_indent:
                in_pts = False
            else:
                i += 1
                continue

        if indent == 0 and ":" in body:
            k, _, v = body.partition(":")
            key = k.strip()
            val = v.strip()
            doc.line_of[key] = i + 1
            if key == "peer-transport-security":
                in_pts = True
                pts_indent = 0
                i += 1
                continue
            if not val:
                # Could be start of block list.
                j = i + 1
                while j < len(lines) and not _strip_comment(lines[j]).strip():
                    j += 1
                if j < len(lines):
                    nxt = _strip_comment(lines[j])
                    nxt_indent = len(nxt) - len(nxt.lstrip(" "))
                    nxt_body = nxt.strip()
                    if nxt_indent > 0 and nxt_body.startswith("- "):
                        cur_list_key = key
                        cur_list_indent = nxt_indent
                        doc.lists[key] = []
                        i += 1
                        continue
                doc.scalars[key] = ""
            elif val.startswith("[") or "," in val:
                doc.lists[key] = _parse_inline_list(val)
            else:
                doc.scalars[key] = _unquote(val)
        i += 1

    return doc


def _is_loopback(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return False
    return host.lower() in LOOPBACK_HOSTS


def _all_urls(doc: ParsedDoc, key: str) -> List[str]:
    if key in doc.lists:
        return [u for u in doc.lists[key] if u]
    s = doc.scalars.get(key, "")
    if not s:
        return []
    return [u.strip() for u in s.split(",") if u.strip()]


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings
    doc = _parse(source)

    listen = _all_urls(doc, "listen-peer-urls")
    advertise = _all_urls(doc, "initial-advertise-peer-urls")
    all_urls = listen + advertise
    if not all_urls:
        return findings

    if all(_is_loopback(u) for u in all_urls):
        return findings

    cert_file = (doc.pts.get("cert-file") or "").strip()
    key_file = (doc.pts.get("key-file") or "").strip()
    pca_raw = (doc.pts.get("peer-client-cert-auth") or "false").strip().lower()
    peer_cert_auth = pca_raw in ("true", "yes", "on", "1")

    line = doc.line_of.get("listen-peer-urls") or doc.line_of.get(
        "initial-advertise-peer-urls", 1
    )

    has_http = any(u.lower().startswith("http://") for u in all_urls)
    if has_http:
        findings.append(
            (line, "etcd peer URL uses plaintext http:// on a non-loopback bind")
        )
        return findings

    missing: List[str] = []
    if not cert_file or not key_file:
        missing.append("peer-transport-security.cert-file/key-file unset")
    if not peer_cert_auth:
        missing.append("peer-transport-security.peer-client-cert-auth=false (default)")
    if missing:
        findings.append(
            (
                line,
                "etcd accepts non-loopback peer traffic without mTLS: "
                + "; ".join(missing),
            )
        )
    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for pat in ("etcd.conf.yml", "etcd.yaml", "etcd.yml", "*etcd*.yaml", "*etcd*.yml"):
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
