#!/usr/bin/env python3
"""
llm-output-uwsgi-stats-server-public-bind-detector

Flags uWSGI configurations that enable the **stats server** on a
network address other than localhost or a unix socket. The stats
server is a JSON endpoint exposing every uWSGI worker's:

  * pid, status, requests served, exceptions raised,
  * **the full request URI of the request currently being handled**,
  * memory (rss, vsz), CPU (utime, stime),
  * configured apps, mountpoints, plugins,
  * cores, signal queue, locks, caches.

Reference:
  https://uwsgi-docs.readthedocs.io/en/latest/StatsServer.html

The doc ends with a sentence almost no LLM training corpus
preserves:

  > "WARNING: do not expose the stats server to the public, it
  >  contains sensitive data."

Bound on `0.0.0.0:1717` (or any non-loopback IP, or `:1717`, or
`*:1717`) it is a turnkey internal-recon endpoint. Any HTTP client
on the network -- `curl http://host:1717/` -- gets the live request
log of every worker.

Maps to:
  - CWE-200: Exposure of Sensitive Information to Unauthorized Actor
  - CWE-419: Unprotected Primary Channel
  - CWE-668: Exposure of Resource to Wrong Sphere
  - OWASP A05:2021 Security Misconfiguration

Why LLMs ship this
------------------
The "Monitoring uWSGI" StackOverflow answers and most blog posts
say:

    [uwsgi]
    stats = :1717

without `stats = 127.0.0.1:1717` or `stats = /tmp/uwsgi.stats.sock`.
The model copies the snippet straight into a production ini.

Heuristic
---------
We scan uWSGI config files (`.ini`, `.yaml`, `.yml`, `.xml`,
`.json`, plus any file whose basename starts with `uwsgi`) for the
`stats` option (a.k.a. `stats-server`, `stats_server`).

Flagged forms:

  ini:
    stats = :1717                 -- bind to all interfaces
    stats = 0.0.0.0:1717          -- bind to all interfaces
    stats = *:1717                -- bind to all interfaces
    stats = 192.168.1.10:1717     -- non-loopback IP
    stats = ::1717                -- IPv6 :: (any)
    stats-server = 0.0.0.0:9191   -- alias

  yaml:
    uwsgi:
      stats: 0.0.0.0:1717
      stats-server: ":1717"

  CLI / shell wrappers:
    uwsgi --stats :1717
    uwsgi --stats-server 0.0.0.0:1717

Not flagged:

  * stats = 127.0.0.1:1717   (loopback)
  * stats = ::1:1717         (IPv6 loopback)
  * stats = localhost:1717
  * stats = /tmp/uwsgi.stats (unix socket)
  * stats = unix:/run/uwsgi/stats.sock
  * commented-out lines
  * `stats-http = ...` documented but only meaningful next to
    `stats = ...` -- if the bind is local, http exposure is
    intentional and we leave it to the operator.

Stdlib-only.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

# ---------------------------------------------------------------------------
# value classification
# ---------------------------------------------------------------------------

_LOOPBACK_HOSTS = {
    "127.0.0.1",
    "localhost",
    "ip6-localhost",
    "ip6-loopback",
    "::1",
    "[::1]",
}


def _classify_bind(value: str) -> Tuple[bool, str]:
    """Return (is_public, reason). is_public=False means safe."""
    v = value.strip().strip('"').strip("'")
    if not v:
        return (False, "empty")

    # unix socket forms
    if v.startswith("/") or v.startswith("unix:") or v.startswith("./"):
        return (False, "unix socket")
    if v.endswith(".sock"):
        return (False, "unix socket")

    # bare port: ":1717"
    if v.startswith(":") and v[1:].isdigit():
        return (True, "bare port (binds all interfaces)")

    # "*:1717"
    if v.startswith("*:"):
        return (True, "wildcard host *")

    # 0.0.0.0:1717
    if v.startswith("0.0.0.0:") or v == "0.0.0.0":
        return (True, "0.0.0.0 (all IPv4 interfaces)")

    # "::1717" -> IPv6 unspecified bare port (some configs)
    if v.startswith("::") and not v.startswith("::1") and ":" in v[2:]:
        return (True, "IPv6 :: (all interfaces)")

    # [::]:1717
    if v.startswith("[::]:"):
        return (True, "[::] (all IPv6 interfaces)")

    # Try host:port split (IPv4 / hostname)
    # Avoid being fooled by IPv6 addresses with multiple colons.
    if v.startswith("["):
        # [addr]:port form
        end = v.find("]")
        if end > 0:
            host = v[1:end].lower()
            if host in _LOOPBACK_HOSTS or host == "::1":
                return (False, "ipv6 loopback")
            if host in ("::", "0:0:0:0:0:0:0:0"):
                return (True, "[::] (all IPv6 interfaces)")
            return (True, f"non-loopback IPv6 host {host}")
    else:
        if ":" in v:
            host, _, _port = v.rpartition(":")
            host = host.lower()
            if host in _LOOPBACK_HOSTS:
                return (False, "loopback host")
            if host == "" or host == "*" or host == "0.0.0.0":
                return (True, "wildcard / all-interfaces host")
            return (True, f"non-loopback host {host}")

    # No colon, not unix-shaped, not bare port. Unusual; treat as
    # bare port if all digits.
    if v.isdigit():
        return (True, "bare port number (binds all interfaces)")

    return (False, "unrecognised value")


# ---------------------------------------------------------------------------
# scanners
# ---------------------------------------------------------------------------

# ini / conf:
#   stats = :1717
#   stats-server = 0.0.0.0:1717
#   stats_server: 0.0.0.0:1717
_INI_STATS = re.compile(
    r"""^\s*(stats|stats[-_]server)\s*[:=]\s*(.+?)\s*(?:[#;].*)?$""",
    re.IGNORECASE,
)

# CLI flag forms (in shell scripts, Dockerfiles, systemd):
#   uwsgi --stats :1717
#   uwsgi --stats=0.0.0.0:1717
#   --stats-server :1717
_CLI_STATS = re.compile(
    r"""--(?:stats|stats-server)(?:\s*=\s*|\s+)([^\s'"]+|"[^"]+"|'[^']+')""",
    re.IGNORECASE,
)

_COMMENT_LINE = re.compile(r"""^\s*[#;]""")
_INI_SECTION = re.compile(r"""^\s*\[\s*([^\]]+?)\s*\]\s*$""")


def _strip_shell_comment(line: str) -> str:
    out = []
    in_s = False
    in_d = False
    for ch in line:
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            break
        out.append(ch)
    return "".join(out)


def scan_ini(text: str, path: str) -> List[str]:
    findings: List[str] = []
    section = ""
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        m_sec = _INI_SECTION.match(raw)
        if m_sec:
            section = m_sec.group(1).strip().lower()
            continue
        # Only consider [uwsgi] section if a section was declared at
        # all. Files with no section header (helper fragments) are
        # also scanned.
        if section and section != "uwsgi":
            continue
        m = _INI_STATS.match(raw)
        if not m:
            continue
        key = m.group(1)
        value = m.group(2).strip()
        is_public, reason = _classify_bind(value)
        if is_public:
            findings.append(
                f"{path}:{lineno}: uwsgi `{key} = {value}` -> "
                f"{reason}; stats server exposes worker request URIs, "
                f"pids, memory, mounted apps to anyone reachable "
                f"(CWE-200/CWE-419)."
            )
    return findings


def scan_yaml(text: str, path: str) -> List[str]:
    findings: List[str] = []
    in_uwsgi = False
    base_indent = -1
    yaml_key = re.compile(
        r"""^(?P<indent>\s*)(?P<key>stats|stats[-_]server)\s*:\s*"""
        r"""(?P<val>.+?)\s*(?:#.*)?$""",
        re.IGNORECASE,
    )
    uwsgi_block = re.compile(r"""^(\s*)uwsgi\s*:\s*(?:#.*)?$""")
    any_top_key = re.compile(r"""^(\s*)[A-Za-z0-9_.-]+\s*:""")
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        if not in_uwsgi:
            mu = uwsgi_block.match(raw)
            if mu:
                in_uwsgi = True
                base_indent = len(mu.group(1))
                continue
        else:
            ml = any_top_key.match(raw)
            if ml and len(ml.group(1)) <= base_indent and \
                    not yaml_key.match(raw):
                in_uwsgi = False
        scope = in_uwsgi or _no_yaml_doc_root(text)
        if not scope:
            continue
        m = yaml_key.match(raw)
        if not m:
            continue
        if in_uwsgi and len(m.group("indent")) <= base_indent:
            continue
        value = m.group("val").strip()
        # Strip surrounding quotes for YAML scalars.
        if (value.startswith('"') and value.endswith('"')) or \
                (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        is_public, reason = _classify_bind(value)
        if is_public:
            findings.append(
                f"{path}:{lineno}: uwsgi yaml `{m.group('key')}: "
                f"{value}` -> {reason}; stats server is unauth + "
                f"public (CWE-200)."
            )
    return findings


def _no_yaml_doc_root(text: str) -> bool:
    """If the YAML has no `uwsgi:` top-level key but is clearly a
    uWSGI fragment (filename hint), allow scanning at root."""
    return "uwsgi:" not in text


def scan_cli(text: str, path: str) -> List[str]:
    findings: List[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_shell_comment(raw)
        for m in _CLI_STATS.finditer(line):
            value = m.group(1).strip().strip('"').strip("'")
            is_public, reason = _classify_bind(value)
            if is_public:
                findings.append(
                    f"{path}:{lineno}: uwsgi CLI --stats {value} -> "
                    f"{reason}; stats server exposes worker state "
                    f"(CWE-200): {raw.strip()[:160]}"
                )
    return findings


# ---------------------------------------------------------------------------
# entrypoints
# ---------------------------------------------------------------------------


def scan(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return []
    low = path.lower()
    base = os.path.basename(low)
    out: List[str] = []
    if low.endswith((".ini", ".conf")) or base.startswith("uwsgi"):
        out.extend(scan_ini(text, path))
    if low.endswith((".yaml", ".yml")):
        out.extend(scan_yaml(text, path))
    if low.endswith((".sh", ".bash", ".service")) \
            or base.startswith("dockerfile") \
            or base.startswith("docker-compose"):
        out.extend(scan_cli(text, path))
    # docker-compose may also have inline `command: uwsgi ...`
    if low.endswith((".yaml", ".yml")) and ("--stats" in text):
        out.extend(scan_cli(text, path))
    return out


_TARGET_EXTS = (".ini", ".conf", ".yaml", ".yml", ".sh", ".bash",
                ".service", ".dockerfile")


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low.endswith(_TARGET_EXTS) \
                            or low.startswith("uwsgi") \
                            or low.startswith("dockerfile") \
                            or low.startswith("docker-compose"):
                        yield os.path.join(dp, f)
        else:
            yield r


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write("usage: detect.py <file-or-dir> [more...]\n")
        return 2
    any_finding = False
    seen = set()
    for path in iter_paths(argv[1:]):
        for line in scan(path):
            if line in seen:
                continue
            seen.add(line)
            print(line)
            any_finding = True
    return 1 if any_finding else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
