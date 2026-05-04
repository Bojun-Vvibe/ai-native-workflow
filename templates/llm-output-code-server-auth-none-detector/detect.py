#!/usr/bin/env python3
"""
llm-output-code-server-auth-none-detector

Flags coder/code-server configurations that disable authentication
on the web UI. code-server is a browser-served VS Code instance,
which means the front page exposes:

  * a full file browser of the host's working directory,
  * an interactive terminal running as the code-server user,
  * the editor itself (read/write any file the process can reach),
  * any extension installed (Remote-SSH, REST clients, etc.).

If `auth: none` (or `--auth none`) is set, anyone who can reach the
listen port owns the host. The official docs are explicit:

    "By default, code-server enables password authentication ...
     You can disable authentication by setting auth to none, but
     this is dangerous and should not be exposed to the network."

But the most-copied snippet from blog posts / Docker tutorials is:

    docker run -p 8080:8080 codercom/code-server --auth none

paired with `--bind-addr 0.0.0.0:8080`. We flag both the `auth` key
in the YAML config (`~/.config/code-server/config.yaml`) and the
CLI / env-var forms.

Maps to:
  - CWE-306: Missing Authentication for Critical Function
  - CWE-862: Missing Authorization
  - CWE-668: Exposure of Resource to Wrong Sphere
  - OWASP A01:2021 Broken Access Control
  - OWASP A05:2021 Security Misconfiguration

Heuristic
---------
Scan files that are likely code-server config / launchers:

  * `*.yaml`, `*.yml` (config.yaml lives there)
  * `*.sh`, `*.bash`, `*.service`
  * `Dockerfile`, `docker-compose.yml`
  * any file basename starting with `code-server` or `coder`
  * `.env` style files (extension `.env`, `.envfile`, `.environment`)

Flagged forms:

  yaml:
    auth: none
    auth: "none"

  CLI:
    code-server --auth none
    code-server --auth=none

  env:
    PASSWORD=
    HASHED_PASSWORD=
  paired with code-server context (basename hint, or sibling
  --auth flag in same file). To stay precise we ONLY flag the
  explicit `auth: none` / `--auth none` / `--auth=none` forms;
  empty PASSWORD is too ambiguous on its own.

Not flagged:
  * auth: password
  * --auth password
  * commented-out lines
  * auth: none in non-code-server contexts (we require a yaml key
    at top level OR a code-server CLI invocation)

Stdlib-only.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List


_COMMENT_LINE = re.compile(r"""^\s*#""")

# YAML key form. We require the key to be at column 0 (top-level)
# OR the file basename to look like code-server config.
_YAML_AUTH = re.compile(
    r"""^(?P<indent>\s*)auth\s*:\s*(?P<val>[^\s#].*?)\s*(?:#.*)?$""",
    re.IGNORECASE,
)

# CLI form. Matches:
#   code-server --auth none
#   code-server --auth=none
#   --auth none      (in a sibling line of a code-server invocation)
_CLI_AUTH = re.compile(
    r"""--auth(?:\s*=\s*|\s+)(?P<val>['"]?[A-Za-z0-9_-]+['"]?)""",
    re.IGNORECASE,
)

# Hint that a CLI line is actually code-server.
_CODE_SERVER_HINT = re.compile(r"""\bcode-server\b""", re.IGNORECASE)


def _strip_quotes(v: str) -> str:
    v = v.strip().strip('"').strip("'")
    return v


def _is_none(v: str) -> bool:
    return _strip_quotes(v).strip().lower() == "none"


def _looks_like_code_server_file(path: str) -> bool:
    base = os.path.basename(path).lower()
    if base.startswith("code-server") or base.startswith("coder"):
        return True
    # Common path: ~/.config/code-server/config.yaml
    return "code-server" in path.lower()


def scan_yaml(text: str, path: str) -> List[str]:
    findings: List[str] = []
    file_hint = _looks_like_code_server_file(path)
    text_hint = _CODE_SERVER_HINT.search(text) is not None
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        m = _YAML_AUTH.match(raw)
        if not m:
            continue
        if not _is_none(m.group("val")):
            continue
        # Require either a code-server file hint OR top-level key
        # (indent == 0). This prevents flagging unrelated yaml that
        # happens to define an `auth: none` field deep in a tree.
        if len(m.group("indent")) > 0 and not (file_hint or text_hint):
            continue
        findings.append(
            f"{path}:{lineno}: code-server `auth: none` -> web UI "
            f"served without authentication; anyone reachable on "
            f"the listen port gets a full editor + terminal "
            f"(CWE-306/CWE-862)."
        )
    return findings


def scan_cli(text: str, path: str) -> List[str]:
    findings: List[str] = []
    file_hint = _looks_like_code_server_file(path)
    text_hint = _CODE_SERVER_HINT.search(text) is not None
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        # We only emit a finding if we can attribute the --auth flag
        # to code-server, either by file hint or by code-server
        # appearing in the same file.
        if not (file_hint or text_hint):
            continue
        for m in _CLI_AUTH.finditer(raw):
            if not _is_none(m.group("val")):
                continue
            findings.append(
                f"{path}:{lineno}: code-server CLI `--auth "
                f"{_strip_quotes(m.group('val'))}` -> editor + "
                f"terminal exposed unauthenticated (CWE-306): "
                f"{raw.strip()[:160]}"
            )
    return findings


def scan_env(text: str, path: str) -> List[str]:
    """
    For env-var-style files, flag a literal `AUTH=none` line in
    files that look like code-server context. (code-server reads
    `AUTH` as an alternative to `--auth`.)
    """
    findings: List[str] = []
    file_hint = _looks_like_code_server_file(path)
    text_hint = _CODE_SERVER_HINT.search(text) is not None
    if not (file_hint or text_hint):
        return findings
    pat = re.compile(
        r"""^\s*AUTH\s*=\s*(?P<val>['"]?[A-Za-z0-9_-]+['"]?)\s*$""",
    )
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        m = pat.match(raw)
        if not m:
            continue
        if not _is_none(m.group("val")):
            continue
        findings.append(
            f"{path}:{lineno}: code-server env `AUTH=none` -> "
            f"unauthenticated editor + terminal (CWE-306)."
        )
    return findings


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
    if low.endswith((".yaml", ".yml")):
        out.extend(scan_yaml(text, path))
    if low.endswith((".sh", ".bash", ".service", ".dockerfile")) \
            or base.startswith("dockerfile") \
            or base.startswith("docker-compose"):
        out.extend(scan_cli(text, path))
    if low.endswith((".yaml", ".yml")) and "--auth" in text:
        out.extend(scan_cli(text, path))
    if low.endswith((".envfile", ".environment")) \
            or base == "envfile" \
            or base == "dotenv" \
            or base.endswith(".envfile"):
        out.extend(scan_env(text, path))
    return out


_TARGET_EXTS = (".yaml", ".yml", ".sh", ".bash", ".service",
                ".dockerfile", ".envfile", ".environment")


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low.endswith(_TARGET_EXTS) \
                            or low.startswith("dockerfile") \
                            or low.startswith("docker-compose") \
                            or low.startswith("code-server") \
                            or low.startswith("coder"):
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
