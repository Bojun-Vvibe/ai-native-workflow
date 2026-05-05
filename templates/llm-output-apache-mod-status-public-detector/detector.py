#!/usr/bin/env python3
"""Detect Apache httpd configs that expose ``mod_status`` (``/server-status``
or ``/server-info``) without an access restriction.

See README.md for the precise rules. Exit code is the count of files
with at least one finding (capped at 255). Stdout lines have the form
``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*server-status-public-allowed")

LOCATION_OPEN_RE = re.compile(
    r"^\s*<\s*Location(Match)?\s+\"?([^\">]+)\"?\s*>", re.IGNORECASE
)
LOCATION_CLOSE_RE = re.compile(r"^\s*</\s*Location(Match)?\s*>", re.IGNORECASE)
SETHANDLER_RE = re.compile(
    r"^\s*SetHandler\s+(server-status|server-info)\b", re.IGNORECASE
)
EXTENDED_STATUS_RE = re.compile(r"^\s*ExtendedStatus\s+On\b", re.IGNORECASE)

# Access control directives that constitute a real restriction.
REQUIRE_RE = re.compile(r"^\s*Require\s+(.+)$", re.IGNORECASE)
ALLOW_FROM_RE = re.compile(r"^\s*Allow\s+from\s+(.+)$", re.IGNORECASE)
DENY_FROM_RE = re.compile(r"^\s*Deny\s+from\s+(.+)$", re.IGNORECASE)
ORDER_RE = re.compile(r"^\s*Order\s+(.+)$", re.IGNORECASE)
AUTH_TYPE_RE = re.compile(r"^\s*AuthType\s+\S+", re.IGNORECASE)
AUTH_USER_FILE_RE = re.compile(r"^\s*AuthUserFile\s+\S+", re.IGNORECASE)


PUBLIC_REQUIRE_TOKENS = {"all", "all granted", "valid-user-any", "any"}
# A "Require all granted" with no other restriction => public.


def _is_public_require(value: str) -> bool:
    v = value.strip().lower()
    if v.startswith("all granted"):
        return True
    if v == "all":
        # legacy: "Require all" alone is not valid; treat as public-ish.
        return True
    return False


def _is_loopback_token(tok: str) -> bool:
    t = tok.strip().lower()
    return t in {
        "127.0.0.1",
        "::1",
        "localhost",
        "local",
        "127.0.0.0/8",
        "::1/128",
    }


def _is_private_cidr(tok: str) -> bool:
    t = tok.strip().lower()
    private_prefixes = (
        "10.",
        "192.168.",
        "172.16.",
        "172.17.",
        "172.18.",
        "172.19.",
        "172.20.",
        "172.21.",
        "172.22.",
        "172.23.",
        "172.24.",
        "172.25.",
        "172.26.",
        "172.27.",
        "172.28.",
        "172.29.",
        "172.30.",
        "172.31.",
        "fd",  # IPv6 ULA fd00::/8
        "fe80",  # link-local
    )
    return any(t.startswith(p) for p in private_prefixes)


class Block:
    __slots__ = (
        "open_line",
        "path",
        "is_match",
        "handler_status",
        "requires",
        "allow_froms",
        "deny_froms",
        "has_order",
        "has_auth",
    )

    def __init__(self, open_line: int, path: str, is_match: bool) -> None:
        self.open_line = open_line
        self.path = path
        self.is_match = is_match
        self.handler_status = False
        self.requires: List[Tuple[int, str]] = []
        self.allow_froms: List[Tuple[int, str]] = []
        self.deny_froms: List[Tuple[int, str]] = []
        self.has_order = False
        self.has_auth = False

    def is_restricted(self) -> bool:
        # Any auth requirement counts as restriction.
        if self.has_auth:
            return True
        # Any Require that is NOT a public catch-all counts.
        for _, val in self.requires:
            if not _is_public_require(val):
                return True
        # Allow from with only loopback / private + matching Order rule
        # is a restriction. We treat any Allow from with a non-"all"
        # token as restrictive enough for our purposes; if "all" appears
        # we do NOT call it restrictive.
        for _, val in self.allow_froms:
            tokens = [t for t in re.split(r"[\s,]+", val) if t]
            if not tokens:
                continue
            if any(t.lower() == "all" for t in tokens):
                continue
            return True
        # Explicit deny + a default-allow elsewhere is hard to model;
        # if there is a `Deny from all` that's a restriction.
        for _, val in self.deny_froms:
            if "all" in val.lower().split():
                return True
        return False

    def public_reason(self) -> str:
        # Identify the most concrete reason this block is public.
        for _, val in self.requires:
            if _is_public_require(val):
                return f"Require {val.strip()}"
        if not self.requires and not self.allow_froms and not self.has_auth:
            return "no Require / Allow / Auth directive"
        for _, val in self.allow_froms:
            tokens = [t.lower() for t in re.split(r"[\s,]+", val) if t]
            if "all" in tokens:
                return "Allow from all"
        return "no effective access restriction"


def scan(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    if SUPPRESS.search(source):
        return findings

    blocks: List[Block] = []
    stack: List[Block] = []

    extended_status_on = False

    for i, raw in enumerate(source.splitlines(), start=1):
        # Strip inline comments only after the directive name to avoid
        # eating quoted '#' chars; httpd configs rarely quote them.
        stripped = raw.split("#", 1)[0]
        if not stripped.strip():
            continue

        m = LOCATION_OPEN_RE.match(stripped)
        if m:
            path = m.group(2).strip()
            is_match = bool(m.group(1))
            blk = Block(open_line=i, path=path, is_match=is_match)
            blocks.append(blk)
            stack.append(blk)
            continue

        if LOCATION_CLOSE_RE.match(stripped):
            if stack:
                stack.pop()
            continue

        if EXTENDED_STATUS_RE.match(stripped):
            extended_status_on = True
            continue

        if not stack:
            # Top-level SetHandler (rare for status, but legal in vhost
            # context). We treat it as a synthetic block covering the
            # enclosing scope.
            m = SETHANDLER_RE.match(stripped)
            if m:
                synthetic = Block(open_line=i, path="<top-level>", is_match=False)
                synthetic.handler_status = True
                blocks.append(synthetic)
            continue

        cur = stack[-1]
        m = SETHANDLER_RE.match(stripped)
        if m:
            cur.handler_status = True
            continue

        m = REQUIRE_RE.match(stripped)
        if m:
            cur.requires.append((i, m.group(1)))
            continue
        m = ALLOW_FROM_RE.match(stripped)
        if m:
            cur.allow_froms.append((i, m.group(1)))
            continue
        m = DENY_FROM_RE.match(stripped)
        if m:
            cur.deny_froms.append((i, m.group(1)))
            continue
        if ORDER_RE.match(stripped):
            cur.has_order = True
            continue
        if AUTH_TYPE_RE.match(stripped) or AUTH_USER_FILE_RE.match(stripped):
            cur.has_auth = True
            continue

    for blk in blocks:
        if not blk.handler_status:
            continue
        if blk.is_restricted():
            continue
        findings.append(
            (
                blk.open_line,
                (
                    f"<Location {blk.path}> exposes mod_status handler "
                    f"with {blk.public_reason()} — server-status/server-info "
                    "publicly reachable"
                ),
            )
        )

    # If ExtendedStatus On is set globally with no status block at all,
    # that's not by itself a vuln (the handler has to be wired up). We
    # do not emit a finding for that case.
    _ = extended_status_on
    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("*.conf", "httpd.conf", "apache2.conf"):
                targets.extend(sorted(path.rglob(ext)))
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
