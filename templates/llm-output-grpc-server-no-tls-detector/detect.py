#!/usr/bin/env python3
"""Detect gRPC server constructions that omit TLS / use insecure credentials.

gRPC servers default to plaintext if no transport credentials are
supplied. LLM-emitted snippets routinely:

* Call `grpc.NewServer()` (Go) with no `grpc.Creds(...)` option.
* Call `grpc.server(...)` (Python) and bind via `add_insecure_port`
  rather than `add_secure_port`.
* Use `grpc.insecure_channel` / `insecure.NewCredentials()` /
  `grpc.InsecureChannelCredentials()` on the *server* side or in
  production wiring.
* Construct a Java `ServerBuilder.forPort(...)` without
  `.useTransportSecurity(...)` / `.sslContext(...)`.
* Construct a Node `new grpc.Server()` and register on
  `grpc.ServerCredentials.createInsecure()`.

Why this matters
----------------

A gRPC server without TLS exposes every RPC payload — including
auth tokens, PII, and internal call metadata — to any on-path
observer. Unlike HTTP/1.1 + TLS-terminating proxy, gRPC is
typically called pod-to-pod and frequently bypasses any ingress
TLS termination, so "the proxy handles TLS" is rarely true for
internal services.

What this flags
---------------

Go (`*.go`):

* `grpc.NewServer(...)` whose argument list contains no
  `grpc.Creds(` token → `grpc-go-server-no-creds`.
* Use of `insecure.NewCredentials()` →
  `grpc-go-insecure-credentials`.
* Use of `grpc.WithInsecure()` → `grpc-go-with-insecure`.

Python (`*.py`):

* `add_insecure_port(` on a server object →
  `grpc-py-add-insecure-port`.
* `grpc.insecure_channel(` in a non-test path →
  `grpc-py-insecure-channel`.

Java (`*.java`):

* `ServerBuilder.forPort(...)` not followed within 6 lines by
  `.useTransportSecurity(` or `.sslContext(` →
  `grpc-java-server-no-tls`.

Node (`*.js`, `*.ts`, `*.mjs`, `*.cjs`):

* `grpc.ServerCredentials.createInsecure(` →
  `grpc-js-server-credentials-insecure`.

What this does NOT flag
-----------------------

* `grpc.NewServer(grpc.Creds(creds))` in Go.
* `server.add_secure_port(...)` in Python.
* `ServerBuilder.forPort(p).useTransportSecurity(certFile, keyFile)`
  in Java within the 6-line window.
* Lines marked with a trailing `# grpc-no-tls-ok` or
  `// grpc-no-tls-ok` comment.
* Patterns inside `#` or `//` comment lines.
* Files under any path segment named `test`, `tests`, `_test`, or
  ending `_test.go` / `.test.js` / `.test.ts`.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 on findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


SUFFIXES = {".py", ".go", ".java", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}

RE_SUPPRESS = re.compile(r"(?:#|//)\s*grpc-no-tls-ok\b")
RE_PY_COMMENT = re.compile(r"^\s*#")
RE_SLASH_COMMENT = re.compile(r"^\s*//")

# Go
RE_GO_NEW_SERVER = re.compile(r"\bgrpc\.NewServer\s*\(")
RE_GO_CREDS = re.compile(r"\bgrpc\.Creds\s*\(")
RE_GO_INSECURE_CREDS = re.compile(r"\binsecure\.NewCredentials\s*\(")
RE_GO_WITH_INSECURE = re.compile(r"\bgrpc\.WithInsecure\s*\(")

# Python
RE_PY_ADD_INSECURE = re.compile(r"\.add_insecure_port\s*\(")
RE_PY_INSECURE_CHANNEL = re.compile(r"\bgrpc\.insecure_channel\s*\(")

# Java
RE_JAVA_FORPORT = re.compile(r"\bServerBuilder\s*\.\s*forPort\s*\(")
RE_JAVA_TLS_OK = re.compile(r"\.\s*(?:useTransportSecurity|sslContext)\s*\(")

# Node
RE_JS_INSECURE = re.compile(r"\bgrpc\.ServerCredentials\.createInsecure\s*\(")

TEST_PATH_PARTS = {"test", "tests", "_test", "__tests__", "testdata"}


def is_test_path(p: Path) -> bool:
    parts = {part.lower() for part in p.parts}
    if parts & TEST_PATH_PARTS:
        return True
    name = p.name.lower()
    if name.endswith("_test.go"):
        return True
    if name.endswith(".test.js") or name.endswith(".test.ts"):
        return True
    if name.endswith(".test.mjs") or name.endswith(".test.cjs"):
        return True
    return False


def is_comment_line(line: str, suffix: str) -> bool:
    if suffix == ".py":
        return bool(RE_PY_COMMENT.match(line))
    return bool(RE_SLASH_COMMENT.match(line))


def collect_call_args(lines, idx, open_paren_pos):
    """Walk forward to find matching close paren; return concatenated arg text."""
    depth = 0
    out = []
    started = False
    for i in range(idx, min(idx + 12, len(lines))):
        s = lines[i] if i != idx else lines[i][open_paren_pos:]
        for ch in s:
            if ch == "(":
                depth += 1
                started = True
                out.append(ch)
                continue
            if ch == ")":
                depth -= 1
                if depth == 0:
                    return "".join(out)
                out.append(ch)
                continue
            if started and depth >= 1:
                out.append(ch)
        out.append("\n")
    return "".join(out)


def scan_file(path: Path):
    findings = []
    if path.suffix not in SUFFIXES:
        return findings
    if is_test_path(path):
        return findings
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    lines = text.splitlines()
    suffix = path.suffix

    for i, line in enumerate(lines):
        if RE_SUPPRESS.search(line):
            continue
        if is_comment_line(line, suffix):
            continue
        ln = i + 1

        if suffix == ".go":
            m = RE_GO_NEW_SERVER.search(line)
            if m:
                args = collect_call_args(lines, i, m.end() - 1)
                if "grpc.Creds(" not in args:
                    findings.append((path, ln, "grpc-go-server-no-creds", line.strip()))
            if RE_GO_INSECURE_CREDS.search(line):
                findings.append((path, ln, "grpc-go-insecure-credentials", line.strip()))
            if RE_GO_WITH_INSECURE.search(line):
                findings.append((path, ln, "grpc-go-with-insecure", line.strip()))

        elif suffix == ".py":
            if RE_PY_ADD_INSECURE.search(line):
                findings.append((path, ln, "grpc-py-add-insecure-port", line.strip()))
            if RE_PY_INSECURE_CHANNEL.search(line):
                findings.append((path, ln, "grpc-py-insecure-channel", line.strip()))

        elif suffix == ".java":
            if RE_JAVA_FORPORT.search(line):
                window = "\n".join(lines[i : i + 7])
                if not RE_JAVA_TLS_OK.search(window):
                    findings.append((path, ln, "grpc-java-server-no-tls", line.strip()))

        elif suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
            if RE_JS_INSECURE.search(line):
                findings.append((path, ln, "grpc-js-server-credentials-insecure", line.strip()))

    return findings


def iter_files(targets):
    for t in targets:
        p = Path(t)
        if p.is_file():
            yield p
        elif p.is_dir():
            for sub in p.rglob("*"):
                if sub.is_file():
                    yield sub


def main(argv):
    if len(argv) < 2:
        print(f"usage: {argv[0]} <file_or_dir> [...]", file=sys.stderr)
        return 2
    findings = []
    for f in iter_files(argv[1:]):
        findings.extend(scan_file(f))
    for path, ln, code, snippet in findings:
        print(f"{path}:{ln}: {code}: {snippet}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
