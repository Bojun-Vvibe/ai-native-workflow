#!/usr/bin/env python3
"""
llm-output-prometheus-pushgateway-no-auth-detector

Flags Prometheus Pushgateway deployments that expose the HTTP push
endpoint (default port 9091) on a public bind address with **no
authentication** -- neither basic_auth, bearer_token, TLS client
cert, nor a `--web.config.file` pointing at a non-empty config.

Pushgateway (`prom/pushgateway`, upstream
github.com/prometheus/pushgateway, v1.x line incl. v1.9.0) ships
**no built-in authentication on /metrics/job/...**. The README is
explicit: "The Pushgateway does not perform any authentication." It
expects either a reverse proxy or a `--web.config.file` web TLS /
basic-auth config (https://prometheus.io/docs/prometheus/latest/configuration/https/).

LLMs nevertheless emit:

    docker run -p 9091:9091 prom/pushgateway
    args: ["--web.listen-address=0.0.0.0:9091"]
    pushgateway --web.listen-address=:9091

...with no `--web.config.file`. Anyone who can reach :9091 can then
POST arbitrary metric series, poison alerting, mask real outages,
and DoS the gateway via unbounded label cardinality.

Maps to:
- CWE-306: Missing Authentication for Critical Function.
- CWE-668: Exposure of Resource to Wrong Sphere.

Stdlib-only.

Heuristic
---------
A file is "pushgateway-related" if it mentions any of:
  - `prom/pushgateway`
  - `pushgateway` as a binary invocation (line starts with or word `pushgateway`)
  - `--web.listen-address` together with `pushgateway`/`prom/pushgateway`/`9091`

Inside such a file (outside `#` / `//` comment lines) we flag:

1. `--web.listen-address=0.0.0.0:<port>` or `--web.listen-address=:<port>`
   (empty host) when no `--web.config.file=<non-empty>` appears in the
   same file.
2. Docker `-p [host:]9091:9091` where host bind is not loopback,
   when image is `prom/pushgateway` and no `--web.config.file` set.
3. docker-compose `ports:` entries publishing `9091:9091` next to a
   `prom/pushgateway` image with no `web.config.file` env / arg.
4. k8s `Service` of type `LoadBalancer` or `NodePort` whose
   `port`/`targetPort` is `9091` in a manifest that references a
   `prom/pushgateway` image and does not set `--web.config.file`.

Each occurrence emits one finding line.

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple


_PUSHGATEWAY_IMAGE = re.compile(r"""\bprom/pushgateway\b""")
_PUSHGATEWAY_BIN = re.compile(r"""(?:^|\s|["'\[])pushgateway(?:\s|$|["'\]])""")

_LISTEN_ADDR_PUBLIC = re.compile(
    r"""--web\.listen-address\s*[=\s]\s*["']?(?:0\.0\.0\.0|::|\*)?:(\d+)"""
)

_WEB_CONFIG_FILE = re.compile(
    r"""--web\.config\.file\s*[=\s]\s*["']?([^\s"'#]+)"""
)

_DOCKER_P = re.compile(
    r"""(?:^|\s)-p\s+(?:([0-9.]+|::|\*):)?(9091):9091\b"""
)

_YAML_PORT_LINE = re.compile(
    r"""^\s*-?\s*(?:"|')?(?:0\.0\.0\.0:)?9091:9091(?:"|')?\s*$"""
)

_LB_OR_NODEPORT = re.compile(r"""\btype\s*:\s*(LoadBalancer|NodePort)\b""")
_PORT_9091 = re.compile(r"""\b(?:port|targetPort)\s*:\s*9091\b""")

_COMMENT_LINE = re.compile(r"""^\s*(#|//)""")


def _strip_comment(line: str) -> str:
    out = []
    in_s = False
    in_d = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            break
        out.append(ch)
        i += 1
    return "".join(out)


def _is_loopback(host: str) -> bool:
    if not host:
        return False
    return host.startswith("127.") or host == "localhost" or host == "::1"


def _is_pushgateway_file(text: str) -> bool:
    if _PUSHGATEWAY_IMAGE.search(text):
        return True
    # Look for pushgateway binary invocation lines
    for raw in text.splitlines():
        line = _strip_comment(raw)
        if _PUSHGATEWAY_BIN.search(line) and (
            "--web.listen-address" in line
            or "--web.config.file" in line
            or "--persistence.file" in line
        ):
            return True
    return False


def _has_web_config_file(text: str) -> bool:
    for raw in text.splitlines():
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_comment(raw)
        m = _WEB_CONFIG_FILE.search(line)
        if m and m.group(1) and m.group(1) not in ("", '""', "''"):
            return True
    return False


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    if not _is_pushgateway_file(text):
        return findings
    has_config = _has_web_config_file(text)
    has_lb_or_nodeport = bool(_LB_OR_NODEPORT.search(text))

    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_comment(raw)

        m = _LISTEN_ADDR_PUBLIC.search(line)
        if m and not has_config:
            findings.append(
                f"{path}:{lineno}: pushgateway --web.listen-address binds "
                f"port {m.group(1)} on all interfaces with no "
                f"--web.config.file (CWE-306/CWE-668): "
                f"{raw.strip()[:160]}"
            )
            continue

        dm = _DOCKER_P.search(line)
        if dm and not has_config:
            host = dm.group(1) or ""
            if not _is_loopback(host):
                findings.append(
                    f"{path}:{lineno}: docker publishes pushgateway port "
                    f"9091 on non-loopback host '{host or '0.0.0.0'}' "
                    f"with no auth config (CWE-306): {raw.strip()[:160]}"
                )
                continue

        if _YAML_PORT_LINE.match(line) and not has_config:
            findings.append(
                f"{path}:{lineno}: docker-compose publishes pushgateway "
                f"port 9091 without loopback bind and without "
                f"--web.config.file (CWE-306): {raw.strip()[:160]}"
            )
            continue

        if has_lb_or_nodeport and _PORT_9091.search(line) and not has_config:
            findings.append(
                f"{path}:{lineno}: kubernetes Service type "
                f"LoadBalancer/NodePort exposes pushgateway port 9091 "
                f"with no --web.config.file (CWE-306/CWE-668): "
                f"{raw.strip()[:160]}"
            )
            continue
    return findings


_TARGET_NAMES = (
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
)
_TARGET_EXTS = (
    ".yaml", ".yml", ".sh", ".bash", ".service", ".tf",
    ".tpl", ".env",
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
