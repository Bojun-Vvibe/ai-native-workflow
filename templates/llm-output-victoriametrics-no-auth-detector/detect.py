#!/usr/bin/env python3
"""
llm-output-victoriametrics-no-auth-detector

Flags VictoriaMetrics single-node (`victoria-metrics`) and cluster
components (`vmselect`, `vminsert`, `vmstorage`, `vmagent`, `vmalert`)
launched on a non-loopback `-httpListenAddr` without ANY of:

  * `-httpAuth.username` + `-httpAuth.password`  (basic auth), OR
  * `-tls` + `-tlsCertFile` + `-tlsKeyFile` (mTLS would also need
    `-mtls`), OR
  * being placed behind `vmauth` (we accept any service name containing
    `vmauth` as a hint that an auth proxy is present).

VictoriaMetrics components ship with NO authentication by default.
The `-httpListenAddr` flag accepts `:8428` / `0.0.0.0:8428` and the
HTTP API exposes:

  * `/api/v1/write`  -- ingest arbitrary metrics (data poisoning).
  * `/api/v1/query`  -- read every metric (information disclosure).
  * `/api/v1/admin/tsdb/delete_series` -- DELETE arbitrary series.
  * `/-/reload`, `/debug/pprof/*`, `/metrics` -- ops endpoints.

A public listener with no auth is therefore a full read+write+delete
surface for the entire metrics store.

Maps to:
- CWE-306: Missing Authentication for Critical Function.
- CWE-284: Improper Access Control.
- CWE-1188: Insecure Default Initialization of Resource.

LLMs ship this misconfig because the VictoriaMetrics quickstart is a
single `docker run -p 8428:8428 victoriametrics/victoria-metrics`
line with no auth flags, and because cluster YAMLs in the upstream
docs use `-httpListenAddr=:8480` style without ever mentioning
`-httpAuth.*`.

Stdlib-only. Reads files passed on argv (recurses into dirs).

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.

Heuristic
---------
We scan for invocations of the VM binaries and look at the surrounding
arg list (same line, a `command:` / `args:` YAML block, or a
`docker run` line). For each invocation we require evidence of EITHER:

  - basic auth (`-httpAuth.username` AND `-httpAuth.password`), OR
  - TLS (`-tls=true` / `-tlsCertFile`), OR
  - the file path / surrounding context references `vmauth`.

Loopback-only listeners (`127.0.0.1:`, `[::1]:`, `localhost:`) are
exempt -- those are sidecar / single-host setups.

If none of those apply AND there is a non-loopback `-httpListenAddr`,
we emit a finding.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_VM_BINARIES = (
    "victoria-metrics",
    "victoria-metrics-prod",
    "vmselect",
    "vminsert",
    "vmstorage",
    "vmagent",
    "vmalert",
)

# Match a binary token (word boundary, may follow `/`, `"`, `'`, space).
_BIN_RE = re.compile(
    r"(?:(?<=^)|(?<=[\s/\"'\[]))"
    r"(?P<bin>victoria-metrics-prod|victoria-metrics|vmselect|"
    r"vminsert|vmstorage|vmagent|vmalert)"
    r"(?=[\s\"'\]\\]|$)"
)

# httpListenAddr value capture. VM accepts `-httpListenAddr=:8428` and
# `-httpListenAddr :8428` and the double-dash variant.
_LISTEN_RE = re.compile(
    r"-{1,2}httpListenAddr(?:\s*[=]\s*|\s+)"
    r"['\"]?(?P<addr>[^\s'\"\]]+)"
)

_HAS_BASIC_USER = re.compile(r"-{1,2}httpAuth\.username\b")
_HAS_BASIC_PASS = re.compile(r"-{1,2}httpAuth\.password\b")
_HAS_TLS = re.compile(
    r"-{1,2}(?:tls(?:CertFile|KeyFile)?|mtls)\b"
)

_VMAUTH_HINT = re.compile(r"\bvmauth\b", re.IGNORECASE)

_LOOPBACK_PREFIXES = ("127.", "localhost:", "[::1]:", "[::1]", "::1:")


def _strip_hash_comments(text: str) -> str:
    out = []
    for line in text.splitlines():
        # Drop everything from an unquoted `#` to EOL. Best-effort:
        # we don't fully parse YAML/shell quoting, but vmauth as a
        # service name/image will not be inside a quoted string in
        # practice.
        in_s = False
        in_d = False
        cut = len(line)
        for i, ch in enumerate(line):
            if ch == "'" and not in_d:
                in_s = not in_s
            elif ch == '"' and not in_s:
                in_d = not in_d
            elif ch == "#" and not in_s and not in_d:
                cut = i
                break
        out.append(line[:cut])
    return "\n".join(out)




def _is_loopback(addr: str) -> bool:
    a = addr.strip()
    if a.startswith(":") or a.startswith("0.0.0.0"):
        return False
    for p in _LOOPBACK_PREFIXES:
        if a.startswith(p):
            return True
    return False


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _gather_context(text: str, bin_pos: int) -> str:
    """
    Return a window of text that should contain the args for this
    binary invocation. We grab from the start of the current line to:

      - the next blank line, OR
      - the next line beginning with a YAML key that is NOT in an
        `args:` / `command:` continuation, OR
      - 40 lines later, whichever first.

    This lets us follow YAML `args:` blocks that span many lines.
    """
    line_start = text.rfind("\n", 0, bin_pos) + 1
    # Walk forward up to 40 lines.
    end = line_start
    lines_seen = 0
    n = len(text)
    while end < n and lines_seen < 40:
        nl = text.find("\n", end)
        if nl == -1:
            end = n
            break
        end = nl + 1
        lines_seen += 1
        # Stop on blank line.
        nxt = text[end:end + 80]
        if nxt.startswith("\n") or nxt.strip() == "":
            # Allow a single blank line then stop.
            break
    return text[line_start:end]


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    seen_positions = set()

    # vmauth-fronting check ignores `#` comments so phrases like
    # "no vmauth here" in a doc line don't suppress findings.
    text_no_comments = _strip_hash_comments(text)
    has_vmauth_global = bool(_VMAUTH_HINT.search(text_no_comments))

    for bm in _BIN_RE.finditer(text):
        bin_name = bm.group("bin")
        bin_pos = bm.start()

        ctx = _gather_context(text, bin_pos)

        # Need a non-loopback httpListenAddr in the context to be a
        # server invocation we care about.
        listen = _LISTEN_RE.search(ctx)
        if not listen:
            continue
        if _is_loopback(listen.group("addr")):
            continue

        # Auth evidence?
        has_basic = bool(
            _HAS_BASIC_USER.search(ctx) and _HAS_BASIC_PASS.search(ctx)
        )
        has_tls = bool(_HAS_TLS.search(ctx))
        # vmauth hint anywhere in the file (operator-level signal),
        # ignoring `#` comments to avoid doc-string false negatives.
        has_vmauth = has_vmauth_global

        if has_basic or has_tls or has_vmauth:
            continue

        ln = _line_of(text, bin_pos)
        key = (path, ln, bin_name)
        if key in seen_positions:
            continue
        seen_positions.add(key)
        findings.append(
            f"{path}:{ln}: {bin_name} on public -httpListenAddr "
            f"{listen.group('addr')!r} with no -httpAuth.username / "
            f"-tls / vmauth fronting (CWE-306/CWE-284, full read+write+"
            f"delete on the metrics API)"
        )

    return findings


_TARGET_EXTS = (
    ".yaml", ".yml", ".sh", ".bash", ".service", ".env",
    ".tf", ".tpl", ".conf",
)
_TARGET_NAMES = (
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low in _TARGET_NAMES or low.startswith("dockerfile"):
                        yield os.path.join(dp, f)
                    elif low.endswith(_TARGET_EXTS):
                        yield os.path.join(dp, f)
        else:
            yield r


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write("usage: detect.py <file-or-dir> [more...]\n")
        return 2
    any_finding = False
    for path in iter_paths(argv[1:]):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            sys.stderr.write(f"warn: cannot read {path}: {e}\n")
            continue
        for line in scan_text(text, path):
            print(line)
            any_finding = True
    return 1 if any_finding else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
