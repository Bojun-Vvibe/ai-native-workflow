#!/usr/bin/env python3
"""
llm-output-jaeger-collector-grpc-no-auth-detector

Flags Jaeger collector / all-in-one deployments that expose the gRPC
span-ingest port (4317 OTLP / 14250 jaeger.proto) on a public bind
address with no authentication mechanism configured.

Jaeger's collector has, historically, no built-in authn/authz on its
ingest endpoints. The upstream docs (jaegertracing/jaeger, README and
`cmd/collector/app/options.go`, v1.x line) explicitly say the
collector "does not perform any authentication" -- it is expected to
sit behind a private network or a sidecar proxy.

Despite that, LLMs routinely emit:

    docker run -p 4317:4317 -p 14250:14250 jaegertracing/all-in-one
    jaeger-collector --collector.grpc-server.host-port=0.0.0.0:14250
    args: ["--collector.grpc-server.host-port=0.0.0.0:14250"]

...and ship it to a cluster reachable from outside the trust boundary.
Anyone who can reach 14250 / 4317 can then inject arbitrary spans,
poison dashboards, exhaust storage, and (via long span tags) push
crafted strings into the org's observability pipeline.

Maps to:
- CWE-306: Missing Authentication for Critical Function (the only
  thing standing between the public internet and your trace store is
  TCP reachability).
- CWE-668: Exposure of Resource to Wrong Sphere.

Stdlib-only. Reads files passed on argv (recurses into dirs and
picks Dockerfile, *.yaml, *.yml, *.sh, *.bash, *.service, *.env,
docker-compose.* and Helm template files).

Heuristic
---------
We flag any of the following textual occurrences (outside `#` / `//`
comments):

1. `--collector.grpc-server.host-port=0.0.0.0:<port>` or `:<port>`
   (no host = bind all interfaces).
2. `--collector.otlp.grpc.host-port=0.0.0.0:<port>` or `:<port>`.
3. Docker `-p <host>:14250` or `-p <host>:4317` where the host bind
   is `0.0.0.0`, `*`, omitted (just `-p 14250:14250`), or a routable
   address (anything that is not `127.`/`localhost`).
4. k8s Service `type: LoadBalancer` or `type: NodePort` whose
   `targetPort` / `port` is 14250 or 4317 in the same document as a
   Jaeger image (`jaegertracing/`).

Each occurrence emits one finding line.

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_GRPC_HOSTPORT = re.compile(
    r"""--collector\.(?:grpc-server|otlp\.grpc)\.host-port\s*[=\s]\s*["']?(?:0\.0\.0\.0|::|\*)?:(\d+)"""
)

# Catch the dangerous default form `--collector.grpc-server.host-port=:14250`
# (empty host = all interfaces).
_GRPC_EMPTY_HOST = re.compile(
    r"""--collector\.(?:grpc-server|otlp\.grpc)\.host-port\s*[=\s]\s*["']?:(?:14250|4317)\b"""
)

# Docker -p form. We only care about the jaeger ingest ports.
# Forms covered:
#   -p 14250:14250
#   -p 0.0.0.0:14250:14250
#   -p 4317:4317
#   -p 1.2.3.4:4317:4317
_DOCKER_P = re.compile(
    r"""(?:^|\s)-p\s+(?:([0-9.]+|::|\*):)?(\d+):(?:14250|4317)\b"""
)

# YAML port mapping that exposes the ingest ports without restricting
# bind address. We require the same file to mention a jaeger image so
# we do not flag every random `14250` port.
_YAML_PORT_LINE = re.compile(
    r"""^\s*-?\s*(?:"|')?(?:0\.0\.0\.0:)?(?:14250|4317):(?:14250|4317)(?:"|')?\s*$"""
)

_JAEGER_IMAGE = re.compile(r"""jaegertracing/(?:all-in-one|jaeger-collector)\b""")

_LOADBALANCER_OR_NODEPORT = re.compile(r"""\btype\s*:\s*(LoadBalancer|NodePort)\b""")
_TARGET_PORT_INGEST = re.compile(r"""\b(?:port|targetPort)\s*:\s*(?:14250|4317)\b""")

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


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    has_jaeger_image = bool(_JAEGER_IMAGE.search(text))
    has_lb_or_nodeport = bool(_LOADBALANCER_OR_NODEPORT.search(text))

    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_comment(raw)

        if _GRPC_EMPTY_HOST.search(line):
            findings.append(
                f"{path}:{lineno}: jaeger collector gRPC host-port bound "
                f"to all interfaces with no auth (CWE-306/CWE-668): "
                f"{raw.strip()[:160]}"
            )
            continue

        m = _GRPC_HOSTPORT.search(line)
        if m:
            findings.append(
                f"{path}:{lineno}: jaeger collector --collector.*grpc*."
                f"host-port exposes ingest port {m.group(1)} on 0.0.0.0 "
                f"with no auth (CWE-306): {raw.strip()[:160]}"
            )
            continue

        dm = _DOCKER_P.search(line)
        if dm:
            host = dm.group(1) or ""
            if not _is_loopback(host):
                findings.append(
                    f"{path}:{lineno}: docker publishes jaeger ingest port "
                    f"{dm.group(2)} on non-loopback host '{host or '0.0.0.0'}'"
                    f" (CWE-306/CWE-668): {raw.strip()[:160]}"
                )
                continue

        if has_jaeger_image and _YAML_PORT_LINE.match(line):
            findings.append(
                f"{path}:{lineno}: docker-compose publishes jaeger ingest "
                f"port without binding to loopback (CWE-306): "
                f"{raw.strip()[:160]}"
            )
            continue

        if has_jaeger_image and has_lb_or_nodeport and _TARGET_PORT_INGEST.search(line):
            findings.append(
                f"{path}:{lineno}: kubernetes Service of type "
                f"LoadBalancer/NodePort exposes jaeger ingest port "
                f"with no auth (CWE-306/CWE-668): {raw.strip()[:160]}"
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
